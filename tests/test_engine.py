import copy
import json
import threading
import time
import unittest
from urllib.parse import quote

from tenantlens.demo import DEMO_TOKENS, demo_project, make_demo_server
from tenantlens.engine import evaluate, run_project
from tenantlens.models import validate_project
from tenantlens.transport import Response
from helpers import running


class Decisions(unittest.TestCase):
    def setUp(self):
        self.case = validate_project(demo_project())["cases"][0]
        self.proof = {"id": "inv-a-101", "organization_id": "org-a"}

    def decision(self, status, data=None, expected="deny"):
        return evaluate(self.case, expected, Response(status, data))[:2]

    def test_forbidden_success_is_violation(self):
        self.assertEqual(self.decision(200, self.proof), ("VIOLATION", "unexpected_access"))

    def test_allowed_success_is_pass(self):
        self.assertEqual(self.decision(200, self.proof, "allow"), ("PASS", "allowed_access"))

    def test_200_without_resource_proof_is_inconclusive(self):
        for data in (None, {}, {"error": "forbidden"}, {"id": "another", "organization_id": "org-a"}):
            with self.subTest(data=data):
                self.assertEqual(self.decision(200, data)[0], "INCONCLUSIVE")

    def test_expired_session_never_counts_as_denial(self):
        self.assertEqual(self.decision(401)[0], "INCONCLUSIVE")

    def test_server_error_never_counts_as_denial(self):
        self.assertEqual(self.decision(500)[0], "ERROR")

    def test_redirect_never_counts_as_denial(self):
        self.assertEqual(self.decision(302)[0], "INCONCLUSIVE")

    def test_explicit_denial_is_pass(self):
        self.assertEqual(self.decision(403)[0], "PASS")

    def test_allowed_request_denied_is_policy_violation(self):
        self.assertEqual(self.decision(403, expected="allow"), ("VIOLATION", "expected_allow_denied"))

    def test_200_denial_requires_configured_proof(self):
        self.case["deny_conditions"] = [{"pointer": "/error", "equals": "forbidden"}]
        self.assertEqual(self.decision(200, {"error": "forbidden"})[0], "PASS")

    def test_conflicting_evidence_is_inconclusive(self):
        self.case["deny_conditions"] = [{"pointer": "/id", "equals": "inv-a-101"}]
        self.assertEqual(self.decision(200, self.proof), ("INCONCLUSIVE", "conflicting_evidence"))

    def test_timeout_is_error(self):
        self.assertEqual(evaluate(self.case, "deny", Response(error="timeout"))[0], "ERROR")


class RealDemoIntegration(unittest.TestCase):
    def demo(self, mode, change=None, credentials=DEMO_TOKENS):
        with running(make_demo_server(mode)) as url:
            project = demo_project(mode, url)
            if change:
                change(project)
            return run_project(project, credentials=credentials, sleeper=lambda _: None)

    def test_vulnerable_cross_tenant_access_is_detected(self):
        result = self.demo("vulnerable")
        self.assertEqual(result["counts"], {"PASS": 6, "VIOLATION": 3, "INCONCLUSIVE": 0, "ERROR": 0})
        self.assertEqual(result["request_count"], 15)
        self.assertTrue(all(r["identity_verified"] and r["baseline_verified"] for r in result["results"]))

    def test_fixed_demo_satisfies_all_nine_controls(self):
        self.assertEqual(self.demo("fixed")["counts"]["PASS"], 9)

    def test_expired_actor_and_its_resource_are_inconclusive(self):
        result = self.demo("expired")
        self.assertEqual(result["counts"]["INCONCLUSIVE"], 5)
        self.assertEqual(result["counts"]["VIOLATION"], 0)
        self.assertFalse(result["identities"]["bora"]["verified"])
        self.assertFalse(result["baselines"]["invoice-b"]["verified"])

    def test_wrong_identity_prevents_false_pass(self):
        def wrong(p):
            p["accounts"][0]["precheck"]["conditions"][0]["equals"] = "different-user"
        result = self.demo("fixed", wrong)
        self.assertEqual(result["counts"]["INCONCLUSIVE"], 5)

    def test_nonexistent_resource_invalidates_positive_baseline(self):
        def missing(p):
            p["cases"][0]["path"] = "/api/invoices/not-present"
        result = self.demo("fixed", missing)
        self.assertFalse(result["baselines"]["invoice-a"]["verified"])
        self.assertTrue(all(r["verdict"] == "INCONCLUSIVE" for r in result["results"] if r["case_id"] == "invoice-a"))

    def test_missing_credentials_do_not_send_anonymous_requests(self):
        result = self.demo("fixed", credentials={})
        self.assertEqual(result["request_count"], 0)
        self.assertEqual(result["counts"]["INCONCLUSIVE"], 9)

    def test_cancel_before_start_performs_no_requests(self):
        cancel = threading.Event()
        cancel.set()
        result = run_project(demo_project(), credentials=DEMO_TOKENS, cancel=cancel)
        self.assertEqual(result["status"], "cancelled")
        self.assertEqual(result["request_count"], 0)
        self.assertEqual(result["completed"], 9)

    def test_secret_in_target_proof_and_snapshot_is_redacted(self):
        secret = "private/value with space"
        project = demo_project()
        project["name"] = secret
        class Fake:
            def get(self, path, token):
                if path == "/api/whoami":
                    who = next(a for a in project["accounts"] if DEMO_TOKENS[a["auth_env"]] == token)
                    return Response(200, {"id": who["id"], "tenant_id": who["tenant_id"]})
                return Response(200, {"id": secret, "organization_id": quote(secret, safe=""), "raw_body_secret": "do-not-persist-me"})
        credentials = copy.deepcopy(DEMO_TOKENS)
        credentials["TENANTLENS_DEMO_AYSE_TOKEN"] = secret
        # Delegate identity selection independently of the replacement token.
        original = Fake.get
        def adapted(instance, path, token):
            return original(instance, path, DEMO_TOKENS["TENANTLENS_DEMO_AYSE_TOKEN"] if token == secret else token)
        Fake.get = adapted
        updates = []
        result = run_project(project, transport=Fake(), credentials=credentials, sleeper=lambda _: None, progress=updates.append)
        encoded = json.dumps([result, updates])
        self.assertNotIn(secret, encoded)
        self.assertNotIn(quote(secret, safe=""), encoded)
        self.assertNotIn("do-not-persist-me", encoded)
        self.assertIn("[redacted]", encoded)

    def test_run_snapshot_does_not_change_with_project(self):
        project = demo_project()
        result = run_project(project, credentials={})
        project["name"] = "changed after run"
        self.assertNotEqual(result["project"]["name"], project["name"])

    def test_prechecks_baselines_and_matrix_share_one_rate_limit(self):
        with running(make_demo_server("fixed")) as url:
            project = demo_project("fixed", url)
            project["settings"]["request_rate"] = 50
            from tenantlens.transport import HTTPTransport
            real = HTTPTransport(validate_project(project))
            starts = []
            class Timed:
                def get(self, path, token):
                    starts.append(time.monotonic())
                    return real.get(path, token)
            run_project(project, credentials=DEMO_TOKENS, transport=Timed())
            self.assertEqual(len(starts), 15)
            self.assertTrue(all(b - a >= 0.018 for a, b in zip(starts, starts[1:])))
