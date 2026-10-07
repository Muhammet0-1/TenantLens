"""Loopback-only same-origin panel server and background run coordinator."""

from __future__ import annotations

import copy
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import hmac
import json
import mimetypes
import os
from pathlib import Path
import secrets
import threading
from urllib.parse import urlsplit, unquote
from uuid import uuid4

from . import __version__
from .engine import run_project, Redactor, environment_secrets, utcnow
from .models import validate_project, ValidationError
from .reporting import html_report, json_report
from .storage import Storage


class Coordinator:
    def __init__(self, store):
        self.store = store
        self.lock = threading.Lock()
        self.active = None
        self.cancel_event = None
        self.thread = None

    def start(self, project):
        with self.lock:
            if self.active:
                raise ValueError("A run is already in progress.")
            rid = uuid4().hex
            self.active = rid
            self.cancel_event = threading.Event()
            cancel = self.cancel_event
            credentials = {a["auth_env"]: os.environ.get(a["auth_env"], "") for a in project["accounts"]}
            clean = Redactor(list(credentials.values()))
            first = clean.clean({"id": rid, "project_id": project["id"], "project_name": project["name"], "project": copy.deepcopy(project), "started_at": utcnow(), "finished_at": None, "status": "running", "total": len(project["cases"]) * len(project["accounts"]), "completed": 0, "request_count": 0, "counts": {k: 0 for k in ("PASS", "VIOLATION", "INCONCLUSIVE", "ERROR")}, "results": [], "identities": {}, "baselines": {}})
            self.store.save_run(first)

            def work():
                try:
                    run_project(project, credentials=credentials, cancel=cancel, progress=self.store.save_run, run_id=rid)
                except Exception:
                    # No exception repr: it may contain user data or credentials.
                    failed = self.store.run(rid)
                    if failed and failed["status"] == "running":
                        failed.update(status="failed", error="internal_error", finished_at=utcnow())
                        self.store.save_run(failed)
                finally:
                    with self.lock:
                        self.active = None
                        self.cancel_event = None

            self.thread = threading.Thread(target=work, daemon=True)
            self.thread.start()
            return rid

    def cancel(self, rid):
        with self.lock:
            if self.active != rid or self.cancel_event is None:
                return False
            self.cancel_event.set()
            return True


def make_panel_server(port=8765, state_dir=".tenantlens", web_dir=None):
    store = Storage(state_dir)
    coordinator = Coordinator(store)
    csrf = secrets.token_urlsafe(32)
    web = Path(web_dir) if web_dir else Path(__file__).resolve().parent / "static"

    class Handler(BaseHTTPRequestHandler):
        server_version = "TenantLens"
        sys_version = ""
        timeout = 10

        def log_message(self, *_):
            pass

        def gate(self, mutate=False):
            port_number = self.server.server_address[1]
            hosts = {f"127.0.0.1:{port_number}", f"localhost:{port_number}"}
            host = self.headers.get("Host", "")
            if host not in hosts:
                self.error(403, "Host is not allowed.")
                return False
            if self.headers.get("Sec-Fetch-Site") == "cross-site":
                self.error(403, "Cross-site requests are not allowed.")
                return False
            incoming_origin = self.headers.get("Origin")
            if incoming_origin and incoming_origin != "http://" + host:
                self.error(403, "Origin is not allowed.")
                return False
            if mutate and not hmac.compare_digest(self.headers.get("X-TenantLens-CSRF", "").encode("utf-8"), csrf.encode("ascii")):
                self.error(403, "Missing or invalid CSRF token.")
                return False
            return True

        def error(self, status, message):
            self.send_json(status, {"error": message})

        def body(self):
            if self.headers.get("Transfer-Encoding"):
                raise ValidationError("Chunked requests are unsupported.")
            if self.headers.get("Content-Type", "").split(";")[0] != "application/json":
                raise ValidationError("Expected application/json.")
            try:
                length = int(self.headers.get("Content-Length", "0"))
            except ValueError as exc:
                raise ValidationError("Invalid Content-Length.") from exc
            if not 0 < length <= 1048576:
                raise ValidationError("Request body must be between 1 byte and 1 MiB.")
            try:
                return json.loads(self.rfile.read(length).decode("utf-8"), parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))
            except (ValueError, UnicodeError, RecursionError) as exc:
                raise ValidationError("Invalid JSON request.") from exc

        def send_bytes(self, status, data, mime, *, attachment=None):
            self.send_response(status)
            self.send_header("Content-Type", mime)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; img-src 'self' data:; object-src 'none'; base-uri 'none'; frame-ancestors 'none'" if not attachment else "default-src 'none'; style-src 'unsafe-inline'; base-uri 'none'; frame-ancestors 'none'")
            if attachment:
                self.send_header("Content-Disposition", f'attachment; filename="{attachment}"')
            self.end_headers()
            try:
                self.wfile.write(data)
            except (BrokenPipeError, ConnectionResetError):
                pass

        def send_json(self, status, value):
            redactor = Redactor(environment_secrets())
            self.send_bytes(status, json.dumps(redactor.clean(value), ensure_ascii=False, allow_nan=False).encode("utf-8"), "application/json; charset=utf-8")

        def do_GET(self):
            if not self.gate():
                return
            path = urlsplit(self.path).path
            if path == "/api/bootstrap":
                self.send_json(200, {"version": __version__, "csrf_token": csrf, "projects": store.projects(), "runs": store.runs(), "active_run": coordinator.active, "credential_state": {a["auth_env"]: bool(os.environ.get(a["auth_env"])) for p in store.projects() for a in p["accounts"]}})
            elif path == "/api/projects":
                self.send_json(200, store.projects())
            elif path == "/api/runs":
                self.send_json(200, store.runs())
            elif path.startswith("/api/runs/"):
                parts = path.strip("/").split("/")
                if len(parts) < 3:
                    self.error(404, "Route not found.")
                    return
                run = store.run(parts[2])
                if run is None:
                    self.error(404, "Run not found.")
                elif len(parts) == 3:
                    self.send_json(200, run)
                elif len(parts) == 4 and parts[3] in ("report.json", "report.html"):
                    kind = parts[3].split(".")[-1]
                    data = json_report(run) if kind == "json" else html_report(run)
                    self.send_bytes(200, data, "application/json; charset=utf-8" if kind == "json" else "text/html; charset=utf-8", attachment=f"tenantlens-{run['id']}.{kind}")
                else:
                    self.error(404, "Route not found.")
            elif path.startswith("/api/"):
                self.error(404, "Route not found.")
            else:
                requested = web / ("index.html" if path == "/" else unquote(path).lstrip("/"))
                try:
                    requested = requested.resolve()
                    if not requested.is_relative_to(web.resolve()) or not requested.is_file():
                        self.error(404, "Static file not found.")
                        return
                    mime = mimetypes.guess_type(requested.name)[0] or "application/octet-stream"
                    self.send_bytes(200, requested.read_bytes(), mime)
                except (ValueError, OSError):
                    self.error(404, "Static file not found.")

        def mutate(self, method):
            if not self.gate(mutate=True):
                return
            path = urlsplit(self.path).path
            try:
                if method == "POST" and path == "/api/validate":
                    project = validate_project(self.body())
                    self.send_json(200, project)
                elif method == "POST" and path == "/api/projects":
                    project = validate_project(self.body())
                    if store.project(project["id"]):
                        self.error(409, "Project ID already exists.")
                        return
                    project = Redactor(environment_secrets()).clean(project)
                    store.save_project(project)
                    self.send_json(201, project)
                elif path.startswith("/api/projects/"):
                    parts = path.strip("/").split("/")
                    pid = parts[2]
                    if len(parts) == 3 and method == "PUT":
                        project = validate_project(self.body())
                        if project["id"] != pid or store.project(pid) is None:
                            raise ValidationError("Project ID does not match an existing project.")
                        project = Redactor(environment_secrets()).clean(project)
                        store.save_project(project)
                        self.send_json(200, project)
                    elif len(parts) == 3 and method == "DELETE":
                        if store.project(pid) is None:
                            self.error(404, "Project not found.")
                            return
                        store.delete_project(pid)
                        self.send_json(200, {"deleted": True})
                    elif len(parts) == 4 and parts[3] == "runs" and method == "POST":
                        project = store.project(pid)
                        if project is None:
                            self.error(404, "Project not found.")
                            return
                        try:
                            rid = coordinator.start(project)
                        except ValueError:
                            self.error(409, "A run is already in progress.")
                            return
                        self.send_json(202, {"id": rid})
                    else:
                        self.error(404, "Route not found.")
                elif method == "POST" and path.startswith("/api/runs/") and path.endswith("/cancel"):
                    rid = path.strip("/").split("/")[2]
                    if coordinator.cancel(rid):
                        self.send_json(200, {"cancelled": True})
                    else:
                        self.error(409, "Run is not active.")
                else:
                    self.error(404, "Route not found.")
            except ValidationError as exc:
                self.error(400, str(exc))
            except (KeyError, IndexError, TypeError, AttributeError, OverflowError, UnicodeError):
                self.error(400, "Invalid project structure.")

        def do_POST(self):
            self.mutate("POST")

        def do_PUT(self):
            self.mutate("PUT")

        def do_DELETE(self):
            self.mutate("DELETE")

    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    server.daemon_threads = True
    server.store = store
    server.coordinator = coordinator
    return server
