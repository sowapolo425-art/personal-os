import json
import base64
import threading
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest
from personal_os.dashboard import make_server
from personal_os.store import Store
from personal_os.importer import parse_import, commit_import
from personal_os.conversations import ingest_conversation


@pytest.fixture
def dashboard(tmp_path):
    store = Store(tmp_path / "vault")
    store.init()
    server = make_server(store.root, 0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    address = f"http://127.0.0.1:{server.server_port}"
    yield store, address
    server.shutdown()
    server.server_close()
    thread.join()


def request(address, path, body=None, headers=None):
    data = None if body is None else json.dumps(body).encode()
    defaults = {"Content-Type": "application/json", "X-Personal-OS": "dashboard", "Origin": address}
    req = Request(address + path, data=data, headers=defaults if headers is None else headers)
    return urlopen(req, timeout=5)


def test_dashboard_reads_existing_mcp_vault(dashboard):
    store, address = dashboard
    record = store.capture("虚构目标", "每周练习两次", "goal")
    with request(address, "/api/snapshot") as response:
        data = json.load(response)
        assert data["total"] == 1 and data["kinds"] == {"goal": 1}
        assert data["records"][0]["id"] == record["id"]
        assert response.headers["Cache-Control"] == "no-store"
    assert json.load(request(address, "/api/record?id=" + record["id"]))["content"] == record["content"]
    assert len(json.load(request(address, "/api/history?id=" + record["id"]))) == 1
    html = request(address, "/").read().decode()
    assert "Personal OS" in html and "待确认草稿" in html
    assert "https://" not in html


def test_dashboard_sensitivity_covers_records_proposals_and_history(dashboard):
    store, address = dashboard
    record = store.capture("PRIVATE", "RESTRICTED_SENTINEL", sensitivity="restricted")
    store.propose("SECRET_PROFILE", "RESTRICTED_SENTINEL", "敏感理由", source_ids=[record["id"]], allow_restricted=True)
    assert "RESTRICTED_SENTINEL" not in request(address, "/api/snapshot").read().decode()
    assert json.load(request(address, "/api/snapshot"))["total"] == 0
    assert json.load(request(address, "/api/snapshot?restricted=1"))["pending"] == 1
    for route in ("record", "history"):
        with pytest.raises(HTTPError) as exc:
            request(address, f"/api/{route}?id=" + record["id"])
        assert exc.value.code == 400


def test_human_review_and_capture(dashboard):
    store, address = dashboard
    p = store.propose("虚构档案", "这是虚构结论", "演示")
    result = json.load(request(address, "/api/review", {"id": p["proposal_id"], "action": "approve"}))
    assert result["state"] == "approved"
    assert store.get(p["record_id"])["status"] == "confirmed"
    json.load(request(address, "/api/capture", {"title": "本地记录", "content": "原文"}))
    assert len(store.search()) == 2


@pytest.mark.parametrize("headers", [
    {"Content-Type": "application/json"},
    {"Content-Type": "application/json", "Origin": "https://attacker.invalid", "X-Personal-OS": "dashboard"},
    {"Host": "attacker.invalid", "Content-Type": "application/json", "Origin": "http://attacker.invalid", "X-Personal-OS": "dashboard"},
])
def test_cross_origin_write_blocked(dashboard, headers):
    store, address = dashboard
    with pytest.raises(HTTPError) as exc:
        request(address, "/api/capture", {"title": "bad", "content": "bad"}, headers)
    assert exc.value.code == 403
    assert store.search() == []


def test_host_rebinding_and_path_traversal_blocked(dashboard):
    _, address = dashboard
    with pytest.raises(HTTPError) as exc:
        request(address, "/api/snapshot", headers={"Host": "external.invalid"})
    assert exc.value.code == 403
    with pytest.raises(HTTPError) as exc:
        request(address, "/api/snapshot", headers={"Origin": "https://external.invalid"})
    assert exc.value.code == 403
    for path in ("/../../pyproject.toml", "/api/record?id=../outside"):
        with pytest.raises(HTTPError):
            request(address, path)


def test_preview_commit_backup_and_restore_http(dashboard):
    store, address = dashboard
    preview = json.load(request(address, "/api/import-preview", {"filename": "fictional.md", "text": "# 虚构导入\n历史资料"}))
    assert store.search(allow_restricted=True) == []
    body = {"preview_id": preview["preview_id"], "keys": [preview["items"][0]["key"]], "sensitivity": "private"}
    assert json.load(request(address, "/api/import-commit", body))["imported"] == 1
    assert json.load(request(address, "/api/import-commit", body))["skipped"] == 1
    with request(address, "/api/backup", {}) as response:
        assert response.headers["Content-Type"] == "application/zip"
        archive = response.read()
    restored = json.load(request(address, "/api/restore-backup", {"data": base64.b64encode(archive).decode()}))
    assert Store(restored["restored_vault"]).search()[0]["excerpt"] == "# 虚构导入\n历史资料"
    assert len(store.search()) == 1


def test_graph_hides_restricted_nodes_and_configuration_uses_current_vault(dashboard):
    store, address = dashboard
    original = store.capture("依据", "用户表达")
    p = store.propose("理解", "确认结论", "理由", source_ids=[original["id"]])
    store.review(p["proposal_id"], True)
    secret = store.capture("受限", "秘密", sensitivity="restricted")
    items = parse_import("old.json", json.dumps({"title": "旧对话", "create_time": 1704067200, "messages": [{"role": "user", "content": "旧原文"}]}))
    imported = commit_import(store, items, [items[0]["key"]], "private")
    old = store.get(imported["record_ids"][0])
    snapshot = json.load(request(address, "/api/snapshot"))
    assert len(snapshot["graph"]["edges"]) == 1
    assert secret["id"] not in {n["id"] for n in snapshot["graph"]["nodes"]}
    assert old["created_at"].startswith("2024")
    assert old["imported_at"] in snapshot["created_dates"]
    config = json.load(request(address, "/api/config"))["mcpServers"]["personal-os"]
    assert str(store.root) in config["args"] and config["args"][-1] == "serve"


def test_conversations_and_scoped_analysis_http(dashboard):
    store, address = dashboard
    saved = ingest_conversation(store, "fictional-client", "c1", "历史", [
        {"message_id": "m1", "role": "user", "content": "希望学绘画"}])
    assert json.load(request(address, "/api/conversations"))[0]["message_count"] == 1
    secret = store.capture("受限", "RESTRICTED_ANALYSIS", sensitivity="restricted")
    body = {"record_ids": saved["record_ids"], "purpose": "分析目标"}
    result = json.load(request(address, "/api/analysis-pack", body))
    assert result["record_count"] == 1 and result["records"][0]["content"] == "希望学绘画"
    assert "RESTRICTED_ANALYSIS" not in json.dumps(result)
    with pytest.raises(HTTPError):
        request(address, "/api/analysis-pack", {"record_ids": [secret["id"]], "purpose": "目标"})
    for value in ("true", 1):
        with pytest.raises(HTTPError):
            request(address, "/api/analysis-pack", {"record_ids": [secret["id"]], "purpose": "目标", "restricted": value})
    assert json.load(request(address, "/api/analysis-pack", {
        "record_ids": [secret["id"]], "purpose": "目标", "restricted": True}))["record_count"] == 1
    with pytest.raises(HTTPError) as error:
        request(address, "/api/analysis-pack", body, headers={"Content-Type": "application/json", "Origin": "https://external.invalid"})
    assert error.value.code == 403
    assert "copy-history-task" in request(address, "/memory.js").read().decode()


def test_docx_upload_preview_and_material_queue_http(dashboard):
    import io
    import zipfile
    store, address = dashboard
    memory = io.BytesIO()
    with zipfile.ZipFile(memory, "w") as archive:
        archive.writestr("word/document.xml", '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body><w:p><w:r><w:t>虚构事务</w:t></w:r></w:p></w:body></w:document>')
    body = {"filename": "fictional.docx", "data": base64.b64encode(memory.getvalue()).decode()}
    preview = json.load(request(address, "/api/import-preview", body))
    assert store.search() == [] and preview["items"][0]["content"] == "虚构事务"
    json.load(request(address, "/api/import-commit", {"preview_id": preview["preview_id"],
        "keys": [preview["items"][0]["key"]], "sensitivity": "private"}))
    sources = json.load(request(address, "/api/extraction-sources"))
    assert len(sources) == 1 and sources[0]["state"] == "needs_extraction"
    assert store.search(kind="profile") == []


@pytest.mark.parametrize("body", [[], None, "text", 42])
def test_invalid_request_envelopes_return_error_without_disconnect(dashboard, body):
    store, address = dashboard
    for endpoint in ("/api/review", "/api/import-preview", "/api/backup"):
        # A literal null needs explicit serialization; request(..., None) otherwise GETs.
        req = Request(address + endpoint, data=json.dumps(body).encode(), headers={
            "Content-Type":"application/json", "X-Personal-OS":"dashboard", "Origin":address})
        with pytest.raises(HTTPError) as error:
            urlopen(req, timeout=5)
        assert error.value.code == 400 and "JSON object" in json.load(error.value)["error"]
    assert store.search() == []
