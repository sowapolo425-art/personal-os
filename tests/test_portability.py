import io
import json
import stat
import zipfile
from pathlib import Path

import pytest
from personal_os.backup import MANIFEST, create_backup, restore_backup
from personal_os.importer import parse_import, preview_import, commit_import
from personal_os.store import Store


@pytest.fixture
def store(tmp_path):
    result = Store(tmp_path / "vault")
    result.init()
    return result


def test_import_preview_subset_and_repeat_are_safe(store):
    conversations = [{"title": title, "messages": [{"role": "user", "content": title},
                     {"role": "assistant", "content": "AI猜测"}]} for title in ("一个想法", "另一个想法")]
    items = parse_import("history.json", json.dumps(conversations, ensure_ascii=False))
    preview = preview_import(store, items)
    assert len(preview) == 2 and store.search() == []
    assert "AI 生成，非用户事实" in preview[0]["content"]
    result = commit_import(store, items, [items[0]["key"]])
    assert result["imported"] == 1
    assert store.search() == []  # default restricted
    r = store.get(result["record_ids"][0], True)
    assert r["status"] == "imported_source" and r["kind"] == "knowledge"
    assert commit_import(store, items, [items[0]["key"]])["skipped"] == 1
    assert preview_import(store, items)[0]["duplicate"]


def test_chatgpt_import_uses_active_branch_and_preserves_source_date():
    mapping = {
        "root": {"parent": None, "message": None},
        "a": {"parent": "root", "message": {"author": {"role": "user"}, "content": {"parts": ["原文"]}}},
        "b": {"parent": "a", "message": {"author": {"role": "assistant"}, "content": {"parts": ["旧分支"]}}},
        "c": {"parent": "a", "message": {"author": {"role": "assistant"}, "content": {"parts": ["当前分支"]}}},
    }
    text = json.dumps([{"title": "对话", "mapping": mapping, "current_node": "c", "create_time": 1704067200}])
    item = parse_import("conversations.json", text)[0]
    assert "旧分支" not in item["content"] and "当前分支" in item["content"]
    assert item["source_created_at"].startswith("2024-01-01")
    mapping["a"]["parent"] = "c"
    with pytest.raises(ValueError, match="cyclic"):
        parse_import("history.json", json.dumps({"mapping": mapping, "current_node": "c"}))


def test_import_rejects_invalid_selection_and_oversize_record(store):
    items = parse_import("notes.md", "# 我的笔记\n原始表达")
    with pytest.raises(ValueError, match="Selection"):
        commit_import(store, items, ["unrelated"])
    with pytest.raises(ValueError):
        parse_import("../outside.md", "text")
    with pytest.raises(ValueError):
        parse_import("notes.txt", "x" * 100001)
    assert store.search() == []


def test_backup_restore_keeps_active_vault_and_preserves_all_layers(store):
    r = store.capture("受限原文", "私有原文", sensitivity="restricted")
    p = store.propose("受限档案", "待确认理解", "理由", source_ids=[r["id"]], allow_restricted=True)
    data = create_backup(store)
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        assert MANIFEST in z.namelist() and ".personal-os/lock" not in z.namelist()
    result = restore_backup(store, data)
    restored = Store(result["restored_vault"])
    assert restored.root.parent == store.root.parent and restored.root != store.root
    assert restored.get(r["id"], True)["content"] == "私有原文"
    assert restored.proposals()[0]["id"] == p["proposal_id"]
    assert (restored.meta / "history" / r["id"] / "1.md").exists()
    assert store.get(r["id"], True)["revision"] == 1
    assert result["active_vault_unchanged"]


def test_corrupt_backup_is_rejected_before_creating_restore_directory(store):
    store.capture("记录", "原始内容")
    good = create_backup(store)
    altered = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(good)) as source, zipfile.ZipFile(altered, "w") as target:
        for name in source.namelist():
            content = source.read(name)
            if name.endswith(".md"):
                content += b"tampered"
            target.writestr(name, content)
    before = set(store.root.parent.iterdir())
    with pytest.raises(ValueError, match="integrity"):
        restore_backup(store, altered.getvalue())
    assert set(store.root.parent.iterdir()) == before
    assert store.search()[0]["excerpt"] == "原始内容"


@pytest.mark.parametrize("name", ["../outside.txt", "/absolute.txt", "C:/outside.txt", "folder\\outside.txt", "folder/./file.txt"])
def test_zip_path_escape_rejected(store, name):
    data = io.BytesIO()
    with zipfile.ZipFile(data, "w") as archive:
        archive.writestr(MANIFEST, '{}')
        archive.writestr(name, 'text')
    raw = data.getvalue()
    if "\\" in name:
        # Windows ZipFile normalizes separators while writing. Craft raw ZIP
        # names to exercise an untrusted archive, not the local writer.
        raw = raw.replace(name.replace("\\", "/").encode(), name.encode())
    with pytest.raises(ValueError, match="Unsafe"):
        restore_backup(store, raw)


def test_zip_symbolic_link_rejected(store):
    data = io.BytesIO()
    info = zipfile.ZipInfo("link")
    info.external_attr = (stat.S_IFLNK | 0o777) << 16
    with zipfile.ZipFile(data, "w") as archive:
        archive.writestr(MANIFEST, '{}')
        archive.writestr(info, '/outside')
    with pytest.raises(ValueError, match="symbolic link"):
        restore_backup(store, data.getvalue())
