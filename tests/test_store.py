import json
import os
import subprocess
from concurrent.futures import ThreadPoolExecutor
import pytest
from personal_os.store import Store


@pytest.fixture
def store(tmp_path):
    s = Store(tmp_path / "vault")
    s.init()
    return s


def test_original_search_and_markdown(store):
    r = store.capture("周末反思", "我想练习长期思考。\n保留原文。", "thought", tags=["成长"])
    assert store.get(r["id"])["content"] == "我想练习长期思考。\n保留原文。"
    assert store.search("成长")[0]["id"] == r["id"]
    assert store.search("长期")[0]["status"] == "self_report"
    assert store.decode(store._path(r).read_text(encoding="utf-8")) == r


def test_profile_requires_local_review(store):
    with pytest.raises(ValueError, match="Profiles"):
        store.capture("推断", "这是 AI 的判断", "profile")
    source = store.capture("原文", "我偏好可自主安排的工作")
    p = store.propose("工作偏好", "偏好自主安排", "依据一次用户表达，需确认", source_ids=[source["id"]])
    assert store.search(kind="profile") == []
    assert store.proposals()[0]["state"] == "pending"
    store.review(p["proposal_id"], True)
    assert store.get(p["record_id"])["status"] == "confirmed"
    assert store.get(p["record_id"])["source_ids"] == [source["id"]]
    with pytest.raises(ValueError, match="already reviewed"):
        store.review(p["proposal_id"], True)


def test_stale_update_is_rejected(store):
    r = store.capture("记录", "第一版")
    a = store.propose("记录", "第二版", "更新", r["id"], 1, kind="record")
    b = store.propose("记录", "另一版", "更新", r["id"], 1, kind="record")
    store.review(a["proposal_id"], True)
    with pytest.raises(ValueError, match="stale"):
        store.review(b["proposal_id"], True)
    assert store.get(r["id"])["content"] == "第二版"
    assert (store.meta / "history" / r["id"] / "1.md").exists()


def test_restricted_does_not_leak_via_search_read_or_sources(store):
    r = store.capture("敏感", "RESTRICTED_BODY", sensitivity="restricted")
    assert store.search("RESTRICTED") == []
    with pytest.raises(ValueError, match="Restricted"):
        store.get(r["id"])
    with pytest.raises(ValueError, match="Restricted"):
        store.propose("档案", "推断", "理由", source_ids=[r["id"]])
    assert store.get(r["id"], True)["content"] == "RESTRICTED_BODY"


def test_restricted_evidence_keeps_derived_profile_restricted(store):
    source = store.capture("敏感来源", "受限原文", sensitivity="restricted")
    p = store.propose("派生结论", "派生资料", "理由", source_ids=[source["id"]], allow_restricted=True)
    store.review(p["proposal_id"], True)
    assert store.search(kind="profile") == []
    assert store.get(p["record_id"], True)["sensitivity"] == "restricted"


def test_reject_delete_and_restore(store):
    r = store.capture("记录", "原始内容")
    p = store.propose("记录", "修改", "理由", r["id"], 1, "record")
    store.review(p["proposal_id"], False)
    assert store.get(r["id"])["content"] == "原始内容"
    with pytest.raises(ValueError, match="conflict"):
        store.delete(r["id"], 2)
    store.delete(r["id"], 1)
    assert store.search() == []
    restored = store.restore(r["id"], 1)
    assert restored["revision"] == 2
    assert store.get(r["id"])["content"] == "原始内容"


@pytest.mark.parametrize("record_id", ["../outside", "C:\\secret", "", "a" * 31])
def test_path_injection_rejected(store, record_id):
    with pytest.raises(ValueError, match="Invalid"):
        store.get(record_id)


def test_audit_excludes_content(store):
    r = store.capture("PRIVATE_TITLE", "PRIVATE_TEXT", source="PRIVATE_SOURCE")
    store.get(r["id"])
    log = (store.meta / "audit.jsonl").read_text(encoding="utf-8")
    assert "PRIVATE_" not in log
    assert all(set(json.loads(line)) == {"time", "action", "id"} for line in log.splitlines())


def test_concurrent_clients_do_not_lose_records(store):
    def capture(i):
        return Store(store.root).capture(f"record {i}", f"body {i}")
    with ThreadPoolExecutor(max_workers=4) as pool:
        records = list(pool.map(capture, range(12)))
    assert len({r["id"] for r in records}) == 12
    assert len(store.search(limit=100)) == 12


def test_symlink_escape_rejected(store, tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    folder = store.root / "01-Inbox"
    folder.rmdir()
    try:
        folder.symlink_to(outside, target_is_directory=True)
    except OSError:
        if os.name != "nt":
            pytest.skip("Creating symlinks requires OS privileges")
        result = subprocess.run(["cmd", "/c", "mklink", "/J", str(folder), str(outside)], capture_output=True)
        if result.returncode:
            pytest.skip("OS does not allow symlinks or junctions")
    with pytest.raises(ValueError, match="escapes|Links"):
        store.capture("test", "must stay local")
    assert not list(outside.iterdir())
