"""Loopback-only, deliberately vulnerable/fixed API fixtures."""

from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit


DEMO_TOKENS = {"TENANTLENS_DEMO_AYSE_TOKEN": "tenantlens-demo-ayse-2026", "TENANTLENS_DEMO_CAN_TOKEN": "tenantlens-demo-can-2026", "TENANTLENS_DEMO_BORA_TOKEN": "tenantlens-demo-bora-2026"}
PEOPLE = [{"id": "ayse", "name": "Ayşe", "tenant_id": "org-a", "roles": ["user"], "auth_env": "TENANTLENS_DEMO_AYSE_TOKEN"}, {"id": "can", "name": "Can", "tenant_id": "org-a", "roles": ["admin"], "auth_env": "TENANTLENS_DEMO_CAN_TOKEN"}, {"id": "bora", "name": "Bora", "tenant_id": "org-b", "roles": ["user"], "auth_env": "TENANTLENS_DEMO_BORA_TOKEN"}]


def demo_project(mode="vulnerable", base_url="http://127.0.0.1:8766"):
    names = {"vulnerable": "Demo · Veri sızıntısı", "fixed": "Demo · Düzeltilmiş", "expired": "Demo · Geçersiz oturum"}
    accounts = [{**a, "precheck": {"path": "/api/whoami", "conditions": [{"pointer": "/id", "equals": a["id"]}, {"pointer": "/tenant_id", "equals": a["tenant_id"]}]}} for a in PEOPLE]
    definitions = [("invoice-a", "Ayşe’nin faturası", "inv-a-101", "org-a", "ayse", "/api/invoices/inv-a-101", ["allow", "allow", "deny"]), ("admin-report", "A şirketi yönetici raporu", "report-a", "org-a", "can", "/api/admin/report", ["deny", "allow", "deny"]), ("invoice-b", "Bora’nın faturası", "inv-b-201", "org-b", "bora", "/api/invoices/inv-b-201", ["deny", "deny", "allow"])]
    cases = [{"id": cid, "name": name, "resource_id": rid, "tenant_id": tenant, "owner_account_id": baseline, "method": "GET", "path": path, "query": {}, "baseline_account": baseline, "permissions": dict(zip((a["id"] for a in PEOPLE), permits)), "success_conditions": [{"pointer": "/id", "equals": rid}, {"pointer": "/organization_id", "equals": tenant}], "deny_statuses": [403, 404], "deny_conditions": []} for cid, name, rid, tenant, baseline, path, permits in definitions]
    return {"schema_version": 1, "id": "demo-" + mode, "name": names[mode], "base_url": base_url, "allowed_origins": [base_url], "settings": {"timeout": 3, "request_rate": 12, "response_size_limit": 262144}, "accounts": accounts, "cases": cases}


def make_demo_server(mode="vulnerable", port=0, tokens=None):
    if mode not in ("vulnerable", "fixed", "expired"):
        raise ValueError("Unknown demo mode.")
    tokens = tokens or DEMO_TOKENS
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def do_GET(self):
            header = self.headers.get("Authorization", "")
            account = next((a for a in PEOPLE if header == "Bearer " + tokens[a["auth_env"]]), None)
            if account is None or (mode == "expired" and account["id"] == "bora"):
                self.send_json(401, {"error": "invalid_session"})
                return
            path = urlsplit(self.path).path
            if path == "/api/whoami":
                self.send_json(200, {"id": account["id"], "tenant_id": account["tenant_id"], "roles": account["roles"]})
            elif path == "/api/admin/report":
                if account["id"] != "can":
                    self.send_json(403, {"error": "forbidden"})
                else:
                    self.send_json(200, {"id": "report-a", "organization_id": "org-a", "total": 4200})
            elif path in ("/api/invoices/inv-a-101", "/api/invoices/inv-b-201"):
                tenant = "org-a" if path.endswith("inv-a-101") else "org-b"
                if mode != "vulnerable" and account["tenant_id"] != tenant:
                    self.send_json(403, {"error": "forbidden"})
                else:
                    self.send_json(200, {"id": path.rsplit("/", 1)[-1], "organization_id": tenant, "amount": 2800, "currency": "TRY"})
            else:
                self.send_json(404, {"error": "not_found"})

        def send_json(self, status, data):
            payload = json.dumps(data).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    server.daemon_threads = True
    return server
