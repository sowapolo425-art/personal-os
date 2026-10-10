"""Local human dashboard. Bound to loopback, no external assets or model calls."""
import json
import webbrowser
from collections import Counter
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib.resources import files
from urllib.parse import parse_qs, urlsplit

from .store import Store, checked_id


def snapshot(store, restricted=False, query="", kind=""):
    if len(query) > 500:
        raise ValueError("Query too long")
    with store.locked():
        records = [r for r in store._all() if restricted or r["sensitivity"] != "restricted"]
        proposals = []
        for path in sorted(store._safe(store.meta / "proposals").glob("*.json")):
            p = json.loads(store._safe(path).read_text(encoding="utf-8"))
            if not restricted and p["record"]["sensitivity"] == "restricted":
                continue
            if p["state"] == "pending":
                before = None
                if p["expected_revision"] is not None:
                    try:
                        before = store._get(p["record"]["id"])
                    except ValueError as exc:
                        if str(exc) != "Record not found":
                            raise
                if before and not restricted and before["sensitivity"] == "restricted":
                    continue
                proposals.append({**p, "before": before})
        matching = [r for r in records if (not kind or r["kind"] == kind)
                    and query.casefold() in (r["title"] + " " + r["content"] + " " + " ".join(r["tags"])).casefold()]
        matching.sort(key=lambda r: r["updated_at"], reverse=True)
        fields = ("id", "title", "kind", "status", "revision", "created_at", "updated_at", "tags", "sensitivity")
        return {
            "total": len(records), "confirmed": sum(r["status"] == "confirmed" for r in records),
            "pending": len(proposals), "kinds": dict(Counter(r["kind"] for r in records)),
            "created_dates": [r["created_at"] for r in records],
            "records": [{k: r[k] for k in fields} | {"excerpt": r["content"][:180]} for r in matching[:200]],
            "matching": len(matching), "proposals": proposals, "restricted": restricted,
        }


def history(store, record_id, restricted=False):
    with store.locked():
        current = store._get(record_id)
        store._visible(current, restricted)
        directory = store._safe(store.meta / "history" / checked_id(record_id))
        records = [store.decode(store._safe(p).read_text(encoding="utf-8")) for p in directory.glob("*.md")]
        return sorted([r for r in records if restricted or r["sensitivity"] != "restricted"], key=lambda r: r["revision"], reverse=True)


def make_server(vault, port=8765):
    store = Store(vault)
    if not store.meta.is_dir():
        raise ValueError("Run init first")
    if not 0 <= port <= 65535:
        raise ValueError("Invalid port")

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            # Do not log personal record IDs, query terms or contents.
            pass

        def send(self, status, body, mime="application/json; charset=utf-8"):
            if not isinstance(body, bytes):
                body = json.dumps(body, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", mime)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Cross-Origin-Resource-Policy", "same-origin")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")
            self.end_headers()
            self.wfile.write(body)

        def valid_host(self):
            port = self.server.server_port
            return self.headers.get("Host") in (f"127.0.0.1:{port}", f"localhost:{port}")

        def do_GET(self):
            origin = self.headers.get("Origin")
            if not self.valid_host() or (origin and origin != "http://" + self.headers.get("Host", "")):
                self.send(403, {"error": "Invalid local host"})
                return
            try:
                url = urlsplit(self.path)
                params = parse_qs(url.query)
                restricted = params.get("restricted", ["0"])[0] == "1"
                assets = {"/": ("index.html", "text/html"), "/app.js": ("app.js", "text/javascript"), "/style.css": ("style.css", "text/css")}
                if url.path in assets:
                    name, mime = assets[url.path]
                    self.send(200, files("personal_os").joinpath("static", name).read_bytes(), mime + "; charset=utf-8")
                elif url.path == "/api/snapshot":
                    self.send(200, snapshot(store, restricted, params.get("q", [""])[0], params.get("kind", [""])[0]))
                elif url.path == "/api/record":
                    self.send(200, store.get(params.get("id", [""])[0], restricted))
                elif url.path == "/api/history":
                    self.send(200, history(store, params.get("id", [""])[0], restricted))
                else:
                    self.send(404, {"error": "Not found"})
            except (ValueError, KeyError, OSError) as exc:
                self.send(400, {"error": str(exc)})

        def do_POST(self):
            origin = self.headers.get("Origin")
            if (not self.valid_host() or origin != "http://" + self.headers.get("Host", "")
                or self.headers.get("X-Personal-OS") != "dashboard"
                or self.headers.get("Content-Type", "").split(";")[0] != "application/json"):
                self.send(403, {"error": "Only this local dashboard may submit changes"})
                return
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if not 1 <= length <= 500_000:
                    raise ValueError("Invalid request size")
                data = json.loads(self.rfile.read(length))
                if self.path == "/api/review":
                    if data.get("action") not in ("approve", "reject"):
                        raise ValueError("Invalid review action")
                    result = store.review(data["id"], data["action"] == "approve")
                elif self.path == "/api/capture":
                    result = store.capture(data["title"], data["content"], data.get("kind", "thought"),
                                           data.get("sensitivity", "private"), source="local dashboard / user input")
                else:
                    self.send(404, {"error": "Not found"})
                    return
                self.send(200, result)
            except (ValueError, KeyError, OSError, TypeError) as exc:
                self.send(400, {"error": str(exc)})

    return ThreadingHTTPServer(("127.0.0.1", port), Handler)


def run(vault, port, open_browser=True):
    server = make_server(vault, port)
    address = f"http://127.0.0.1:{server.server_port}"
    print(f"Personal OS dashboard: {address}\nPress Ctrl+C to stop.", flush=True)
    if open_browser:
        webbrowser.open(address)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
