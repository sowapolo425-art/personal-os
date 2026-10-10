import json
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor

import pytest

from personal_os.store import Store
from personal_os.conversations import ingest_conversation, list_conversations, mark_processed, analysis_pack
from personal_os.backup import create_backup, restore_backup


@pytest.fixture
def store(tmp_path):
    store = Store(tmp_path / "vault")
    store.init()
    return store


def submit(store, agent="codex/work", content="我想每周读一本书", role="user", **kwargs):
    return ingest_conversation(store, agent, "session-1", "虚构对话", [
        {"message_id": "m1", "role": role, "content": content}], **kwargs)


def test_cross_agent_provenance_and_repeat_safe_intake(store):
    first = submit(store)
    assert first["saved"] == 1
    repeat = submit(store)
    assert repeat["skipped"] == 1 and repeat["record_ids"] == first["record_ids"]
    second = submit(store, agent="claude/project")
    assert second["saved"] == 1 and second["record_ids"] != first["record_ids"]
    rows = list_conversations(store)
    assert {r["agent"] for r in rows} == {"codex/work", "claude/project"}
    record = store.get(first["record_ids"][0])
    assert record["status"] == "conversation_source"
    assert record["conversation"]["role"] == "user"
    assert store.search(kind="profile") == []


def test_concurrent_agents_repeat_same_intake_without_duplicates(store):
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(lambda _: submit(Store(store.root)), range(12)))
    assert sum(r["saved"] for r in results) == 1
    assert len({r["record_ids"][0] for r in results}) == 1
    assert list_conversations(store)[0]["message_count"] == 1


def test_append_and_speaker_changes_require_new_extraction(store):
    first = submit(store)["conversation"]
    mark_processed(store, first["agent"], first["conversation_id"], first["fingerprint"])
    appended = ingest_conversation(store, "codex/work", "session-1", "虚构对话", [
        {"message_id": "m2", "role": "assistant", "content": "建议先尝试"}])
    assert appended["conversation"]["message_count"] == 2
    assert appended["conversation"]["state"] == "needs_extraction"
    changed = submit(store, role="assistant")
    assert changed["saved"] == 1
    assert store.get(changed["record_ids"][0])["conversation"]["role"] == "assistant"


def test_checkpoint_invalidates_on_append_or_edit_and_survives_backup(store):
    first = submit(store)["conversation"]
    mark_processed(store, first["agent"], first["conversation_id"], first["fingerprint"])
    assert list_conversations(store)[0]["state"] == "processed"
    submit(store)
    assert list_conversations(store)[0]["state"] == "processed"
    submit(store, content="改成每月读一本书")
    latest = list_conversations(store)[0]
    assert latest["state"] == "needs_extraction" and latest["saved_versions"] == 2
    assert store.get(latest["record_ids"][0])["content"] == "改成每月读一本书"
    with pytest.raises(ValueError, match="changed"):
        mark_processed(store, first["agent"], first["conversation_id"], first["fingerprint"])
    mark_processed(store, latest["agent"], latest["conversation_id"], latest["fingerprint"])
    restored = Store(restore_backup(store, create_backup(store))["restored_vault"])
    assert list_conversations(restored)[0]["state"] == "processed"


def test_restricted_whole_conversation_does_not_leak_or_downgrade(store):
    submit(store)
    ingest_conversation(store, "codex/work", "session-1", "秘密标题", [
        {"message_id": "m2", "role": "user", "content": "受限原文"}], "restricted")
    assert list_conversations(store) == []
    with pytest.raises(ValueError, match="Restricted"):
        submit(store)
    result = ingest_conversation(store, "codex/work", "session-1", "新批次", [
        {"message_id": "m3", "role": "assistant", "content": "建议"}], allow_restricted=True)
    assert store.get(result["record_ids"][0], True)["sensitivity"] == "restricted"
    with pytest.raises(ValueError):
        mark_processed(store, "codex/work", "session-1", "bad")


def test_insights_keep_claim_type_evidence_and_human_review(store):
    user = submit(store)["record_ids"][0]
    assistant = submit(store, agent="other", role="assistant", content="建议读十本书")["record_ids"][0]
    with pytest.raises(ValueError, match="user-origin"):
        store.propose("错误事实", "读十本书", "来源", source_ids=[assistant], claim_type="user_statement")
    with pytest.raises(ValueError, match="evidence"):
        store.propose("无证据", "猜测", "原因", claim_type="inference")
    proposal = store.propose("阅读目标", "每周读一本书", "用户表达", kind="goal",
                             source_ids=[user], claim_type="user_statement")
    assert store.search(kind="goal") == []
    store.review(proposal["proposal_id"], True)
    record = store.get(proposal["record_id"])
    assert record["claim_type"] == "user_statement" and record["source_ids"] == [user]
    update = store.propose("阅读目标", "目标可能过于密集", "AI 分析", record["id"], 1,
                           "goal", source_ids=[assistant], claim_type="inference")
    pending = next(p for p in store.proposals() if p["id"] == update["proposal_id"])
    assert pending["record"]["source_ids"] == [user, assistant]
    store.review(update["proposal_id"], True)
    assert store.get(record["id"])["claim_type"] == "inference"
    assert store.decode((store.meta / "history" / record["id"] / "1.md").read_text(encoding="utf-8"))["claim_type"] == "user_statement"


@pytest.mark.parametrize("messages", [[], [{"message_id":"1","role":"system","content":"x"}],
    [{"message_id":"1","role":"user","content":"x"},{"message_id":"1","role":"assistant","content":"y"}],
    [{"message_id":"1","role":"user","content":""}], [{"message_id":"1","role":"user","content":"x"}, None]])
def test_invalid_batch_writes_nothing(store, messages):
    with pytest.raises(ValueError):
        ingest_conversation(store, "agent", "c", "title", messages)
    assert store.search() == []


def test_scoped_analysis_export_and_cli_no_overwrite(store, tmp_path):
    first = submit(store)["record_ids"][0]
    secret = store.capture("秘密", "不应默认导出", sensitivity="restricted")
    pack = analysis_pack(store, [first], "分析目标")
    assert pack["record_count"] == 1 and pack["records"][0]["id"] == first
    assert secret["content"] not in json.dumps(pack, ensure_ascii=False)
    with pytest.raises(ValueError, match="Restricted"):
        analysis_pack(store, [secret["id"]], "分析")
    with pytest.raises(ValueError):
        analysis_pack(store, [first, first], "分析")
    output = tmp_path / "analysis.json"
    command = [sys.executable, "-m", "personal_os.cli", "--vault", str(store.root),
               "analysis-pack", "--ids", first, "--purpose", "分析", "--output", str(output)]
    result = subprocess.run(command, capture_output=True, text=True, encoding="utf-8")
    assert result.returncode == 0, result.stderr
    assert json.loads(output.read_text(encoding="utf-8"))["record_count"] == 1
    assert subprocess.run(command, capture_output=True).returncode == 1
