import copy
import http.client
import json
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch

from tenantlens.demo import DEMO_TOKENS, demo_project, make_demo_server
from tenantlens.engine import run_project
from tenantlens.models import validate_project
from tenantlens.reporting import html_report, json_report
from tenantlens.server import make_panel_server
from tenantlens.storage import Storage
from helpers import running


class LocalAPI(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.server = make_panel_server(0, self.temp.name)
        self.context = running(self.server)
        self.context.__enter__()
        self.addCleanup(self.context.__exit__, None, None, None)
        self.port = self.server.server_address[1]
        self.csrf = self.request("GET", "/api/bootstrap")[1]["csrf_token"]

    def request(self, method, path, body=None, headers=None):
        headers = dict(headers or {})
        if body is not None:
            headers.setdefault("Content-Type", "application/json")
            body = json.dumps(body)
        connection = http.client.HTTPConnection("127.0.0.1", self.port, timeout=3)
        connection.request(method, path, body=body, headers=headers)
        response = connection.getresponse()
        raw = response.read()
        result = json.loads(raw) if response.getheader("Content-Type", "").startswith("application/json") else raw
        connection.close()
        return response.status, result

    def mutation(self, method, path, body=None):
        return self.request(method, path, body, {"X-TenantLens-CSRF": self.csrf})

    def test_mutation_requires_csrf(self):
        self.assertEqual(self.request("POST", "/api/projects", demo_project())[0], 403)

    def test_non_ascii_csrf_is_rejected_cleanly(self):
        self.assertEqual(self.request("POST", "/api/projects", demo_project(), {"X-TenantLens-CSRF": "é"})[0], 403)

    def test_incomplete_routes_do_not_crash_the_server(self):
        self.assertEqual(self.request("GET", "/api/runs/")[0], 404)
        self.assertEqual(self.mutation("POST", "/api/projects/", {})[0], 400)
        self.assertEqual(self.request("GET", "/api/bootstrap")[0], 200)

    def test_browser_test_configuration_is_not_treated_as_a_secret(self):
        with patch.dict("os.environ", {"TENANTLENS_TEST_PORT": str(self.port)}):
            p = demo_project(base_url=f"http://127.0.0.1:{self.port}")
            self.assertEqual(self.mutation("POST", "/api/validate", p)[1]["base_url"], p["base_url"])

    def test_wrong_host_is_rejected(self):
        self.assertEqual(self.request("GET", "/api/bootstrap", headers={"Host": "evil.test"})[0], 403)

    def test_cross_origin_and_cross_site_requests_are_rejected(self):
        for headers in ({"Origin": "https://evil.test"}, {"Sec-Fetch-Site": "cross-site"}):
            self.assertEqual(self.request("GET", "/api/bootstrap", headers=headers)[0], 403)

    def test_validation_does_not_persist_project(self):
        self.assertEqual(self.mutation("POST", "/api/validate", demo_project())[0], 200)
        self.assertEqual(self.server.store.projects(), [])

    def test_project_creation_update_and_deletion(self):
        project = demo_project()
        self.assertEqual(self.mutation("POST", "/api/projects", project)[0], 201)
        self.assertEqual(self.mutation("POST", "/api/projects", project)[0], 409)
        project["name"] = "renamed"
        self.assertEqual(self.mutation("PUT", "/api/projects/" + project["id"], project)[0], 200)
        self.assertEqual(self.request("GET", "/api/projects")[1][0]["name"], "renamed")
        self.assertEqual(self.mutation("DELETE", "/api/projects/" + project["id"])[0], 200)
        self.assertEqual(self.server.store.projects(), [])

    def test_malformed_project_does_not_crash_or_echo_secret(self):
        project = demo_project()
        project["accounts"] = "secret-user-content"
        status, result = self.mutation("POST", "/api/projects", project)
        self.assertEqual(status, 400)
        self.assertNotIn("secret-user-content", json.dumps(result))

    def test_known_environment_secret_is_redacted_before_storage(self):
        project = demo_project()
        project["name"] = "test-very-private-token"
        with patch.dict("os.environ", {"TENANTLENS_TEST_TOKEN": project["name"]}):
            self.mutation("POST", "/api/projects", project)
            self.assertNotIn(project["name"], Path(self.server.store.path).read_bytes().decode("utf-8", errors="ignore"))
            self.assertNotIn(project["name"], json.dumps(self.request("GET", "/api/bootstrap")[1]))

    def test_static_traversal_cannot_read_source_files(self):
        self.assertEqual(self.request("GET", "/%2e%2e/models.py")[0], 404)

    def test_background_run_and_report_routes(self):
        with running(make_demo_server("fixed")) as url, patch.dict("os.environ", DEMO_TOKENS):
            project = demo_project("fixed", url)
            project["settings"]["request_rate"] = 50
            self.mutation("POST", "/api/projects", project)
            status, body = self.mutation("POST", "/api/projects/" + project["id"] + "/runs", {})
            self.assertEqual(status, 202)
            rid = body["id"]
            deadline = time.monotonic() + 3
            while time.monotonic() < deadline:
                run = self.request("GET", "/api/runs/" + rid)[1]
                if run["status"] != "running":
                    break
                time.sleep(0.02)
            self.assertEqual(run["status"], "completed")
            self.assertEqual(run["counts"]["PASS"], 9)
            report = self.request("GET", "/api/runs/" + rid + "/report.json")[1]
            self.assertEqual(report["id"], rid)
            self.assertIn(b"TenantLens", self.request("GET", "/api/runs/" + rid + "/report.html")[1])
            encoded = json.dumps(run)
            self.assertTrue(all(token not in encoded for token in DEMO_TOKENS.values()))


class PersistenceAndReports(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.store = Storage(self.temp.name)
        self.project = validate_project(demo_project())
        self.run = run_project(self.project, credentials={})

    def test_completed_snapshot_is_immutable(self):
        self.store.save_run(self.run)
        with self.assertRaises(ValueError):
            self.store.save_run(self.run)

    def test_project_changes_and_deletion_preserve_history(self):
        self.store.save_project(self.project)
        self.store.save_run(self.run)
        self.project["name"] = "changed"
        self.store.save_project(self.project)
        self.store.delete_project(self.project["id"])
        self.assertEqual(self.store.run(self.run["id"])["project_name"], self.run["project_name"])

    def test_restart_marks_running_work_interrupted(self):
        self.run["status"] = "running"
        self.store.save_run(self.run)
        reopened = Storage(self.temp.name)
        self.assertEqual(reopened.run(self.run["id"])["status"], "interrupted")

    def test_html_escapes_project_and_evidence(self):
        self.run["project_name"] = '<img src=x onerror="alert(1)">'
        self.run["results"][0]["evidence"] = [{"pointer": "/id", "expected": "<script>evil</script>", "observed": "<svg onload=evil>", "matched": False}]
        html = html_report(self.run).decode()
        self.assertNotIn("<img src=x", html)
        self.assertNotIn("<script>evil", html)
        self.assertIn("&lt;script&gt;evil", html)

    def test_json_report_roundtrips_snapshot(self):
        self.assertEqual(json.loads(json_report(self.run)), self.run)
