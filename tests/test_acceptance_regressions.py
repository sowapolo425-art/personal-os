"""Regressions found while exercising complete user workflows."""
import io
import json
import hashlib
import zipfile
from types import SimpleNamespace

import pytest

from personal_os.store import Store
from personal_os.conversations import ingest_conversation, list_conversations
from personal_os.importer import parse_import, commit_import
from personal_os.documents import parse_document
from personal_os.backup import MANIFEST, restore_backup


@pytest.fixture
def store(tmp_path):
    store = Store(tmp_path / "vault")
    store.init()
    return store


def test_review_rejects_revision_changes_to_existing_evidence(store):
    source = store.capture("原话", "我喜欢绘画")
    p = store.propose("偏好", "喜欢绘画", "依据", source_ids=[source["id"]], claim_type="user_statement")
    store.review(p["proposal_id"], True)
    # Changing the underlying source invalidates a pending update to an insight.
    update = store.propose("偏好", "仍喜欢绘画", "更新", p["record_id"], 1, source_ids=[source["id"]])
    source_update = store.propose("原话", "原话已修改", "修正", source["id"], 1, "record")
    store.review(source_update["proposal_id"], True)
    with pytest.raises(ValueError, match="evidence|Evidence"):
        store.review(update["proposal_id"], True)


def test_review_rejects_missing_evidence(store):
    source = store.capture("原话", "希望读书")
    proposal = store.propose("目标", "读书", "依据", source_ids=[source["id"]], claim_type="inference")
    store.delete(source["id"], 1)
    with pytest.raises(ValueError, match="evidence|Evidence"):
        store.review(proposal["proposal_id"], True)
    assert store.search(kind="profile") == []


def test_review_rejects_evidence_that_changed_privacy_after_drafting(store):
    source = store.capture("原话", "保密计划")
    proposal = store.propose("目标", "保密计划", "依据", source_ids=[source["id"]])
    change = store.propose("原话", "保密计划", "调整隐私", source["id"], 1, "record", sensitivity="restricted")
    store.review(change["proposal_id"], True)
    with pytest.raises(ValueError, match="evidence|Evidence"):
        store.review(proposal["proposal_id"], True)


def test_chat_original_cannot_be_overwritten_by_an_insight(store):
    saved = ingest_conversation(store, "fictional", "session", "原文", [
        {"message_id": "1", "role": "user", "content": "希望读书"}])
    record_id = saved["record_ids"][0]
    with pytest.raises(ValueError, match="original|Original"):
        store.propose("摘要", "读书偏好", "提取", record_id, 1, "record")
    assert list_conversations(store)[0]["message_count"] == 1


def test_identical_conversations_keep_their_separate_titles_and_dates(store):
    items = parse_import("history.json", json.dumps([
        {"id": "a", "title": "一月", "create_time": 1704067200, "messages": [{"role":"user","content":"我想读书"}]},
        {"id": "b", "title": "二月", "create_time": 1706745600, "messages": [{"role":"user","content":"我想读书"}]}]))
    assert len(items) == 2
    result = commit_import(store, items, [i["key"] for i in items], "private")
    assert result["imported"] == 2
    assert {store.get(rid)["title"] for rid in result["record_ids"]} == {"一月", "二月"}
    assert commit_import(store, items, [i["key"] for i in items], "private")["skipped"] == 2


def test_identical_docx_chunks_are_not_dropped():
    memory = io.BytesIO()
    with zipfile.ZipFile(memory, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("word/document.xml", '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body><w:p><w:r><w:t>'+('x' * 200000)+'</w:t></w:r></w:p></w:body></w:document>')
    items = parse_document("repeated.docx", memory.getvalue())
    assert len(items) == 2 and sum(len(i["content"]) for i in items) == 200000


def test_equal_timestamps_use_ingestion_order_not_random_ids(store, monkeypatch):
    import personal_os.store as store_module
    monkeypatch.setattr(store_module, "now", lambda: "2026-10-10T00:00:00+00:00")
    identifiers = iter(["f" * 32, "a" * 32])
    monkeypatch.setattr(store_module.uuid, "uuid4", lambda: SimpleNamespace(hex=next(identifiers)))
    args = (store, "agent", "session", "title")
    ingest_conversation(*args, [{"message_id":"1", "role":"user", "content":"旧版本"}])
    new = ingest_conversation(*args, [{"message_id":"1", "role":"user", "content":"新版本"}])
    assert list_conversations(store)[0]["record_ids"] == new["record_ids"]


def test_docx_tabs_and_line_breaks_preserve_separate_values():
    memory = io.BytesIO()
    with zipfile.ZipFile(memory, "w") as archive:
        archive.writestr("word/document.xml", '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body><w:p><w:r><w:t>first</w:t><w:tab/><w:t>second</w:t><w:br/><w:t>third</w:t></w:r></w:p></w:body></w:document>')
    assert parse_document("spacing.docx", memory.getvalue())[0]["content"] == "first\tsecond\nthird"


def test_mixed_user_and_assistant_sources_can_ground_a_user_statement(store):
    saved = ingest_conversation(store, "agent", "s", "title", [
        {"message_id":"1", "role":"user", "content":"我希望读书"},
        {"message_id":"2", "role":"assistant", "content":"建议先列书单"}])
    proposal = store.propose("目标", "希望读书", "用户直接表达，AI 回复仅为上下文", source_ids=saved["record_ids"], claim_type="user_statement")
    store.review(proposal["proposal_id"], True)
    assert store.get(proposal["record_id"])["claim_type"] == "user_statement"


def test_import_upgrade_reuses_legacy_record_but_recovers_missing_locations(store):
    raw = store._new("二月", "用户原文：\n我想读书", "knowledge", "private", [],
                     "local import / history.json", "imported_source")
    raw["source_created_at"] = "2024-02-01T00:00:00+00:00"
    with store.locked():
        store._save(raw)
    items = parse_import("history.json", json.dumps([
        {"id":"a","title":"一月","create_time":1704067200,"messages":[{"role":"user","content":"我想读书"}]},
        {"id":"b","title":"二月","create_time":1706745600,"messages":[{"role":"user","content":"我想读书"}]}]))
    result = commit_import(store, items, [i["key"] for i in items], "private")
    assert result["imported"] == 1 and result["skipped"] == 1
    assert len(store.search()) == 2


def archive_with_entries(entries):
    memory = io.BytesIO()
    manifest = {"format":"personal-os-backup", "version":1, "files":[]}
    with zipfile.ZipFile(memory, "w") as archive:
        for name, content in entries:
            archive.writestr(name, content)
            manifest["files"].append({"path":name,"size":len(content),"sha256":hashlib.sha256(content).hexdigest()})
        archive.writestr(MANIFEST, json.dumps(manifest))
    return memory.getvalue()


@pytest.mark.parametrize("entries", [[("notes/a.txt",b"first"),("NOTES/A.TXT",b"second")],
    [("notes/CON.txt",b"device")], [("notes/end. ",b"trailing")]],
    ids=["case-collision","device-name","trailing-space"])
def test_nonportable_restore_rejected_before_creating_a_vault(store, entries):
    before = set(store.root.parent.iterdir())
    with pytest.raises(ValueError):
        restore_backup(store, archive_with_entries(entries))
    assert set(store.root.parent.iterdir()) == before
