import json
import threading
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest
from personal_os.dashboard import make_server
from personal_os.store import Store


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
