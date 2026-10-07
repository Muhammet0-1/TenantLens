import unittest
from tenantlens.demo import demo_project
from tenantlens.models import ValidationError, validate_project, resolve_pointer, compare_conditions, origin


class Configuration(unittest.TestCase):
    def rejected(self, change):
        project = demo_project()
        change(project)
        with self.assertRaises((ValidationError, ValueError)):
            validate_project(project)

    def test_token_values_are_not_a_supported_schema_field(self):
        self.rejected(lambda p: p["accounts"][0].update(token="secret"))

    def test_credentials_embedded_in_origin_are_rejected(self):
        self.rejected(lambda p: p.update(base_url="https://user:pass@example.com"))

    def test_absolute_and_protocol_relative_case_paths_are_rejected(self):
        for path in ("https://other.test/x", "//other.test/x", "/a?token=x", "/a#fragment", "/a\\b"):
            with self.subTest(path=path):
                self.rejected(lambda p: p["cases"][0].update(path=path))

    def test_unknown_permissions_are_rejected(self):
        self.rejected(lambda p: p["cases"][0]["permissions"].update(unknown="allow"))

    def test_baseline_must_be_an_allowed_actor(self):
        self.rejected(lambda p: p["cases"][0].update(baseline_account="bora"))

    def test_401_and_500_cannot_be_denial_statuses(self):
        for status in (401, 500):
            self.rejected(lambda p: p["cases"][0].update(deny_statuses=[status]))

    def test_write_methods_are_rejected(self):
        self.rejected(lambda p: p["cases"][0].update(method="POST"))

    def test_credentials_in_query_keys_are_rejected(self):
        self.rejected(lambda p: p["cases"][0].update(query={"api_key": "secret"}))

    def test_origin_allowlist_must_contain_target(self):
        self.rejected(lambda p: p.update(allowed_origins=["https://other.test"]))

    def test_malformed_allowlist_is_rejected(self):
        self.rejected(lambda p: p.update(allowed_origins=[123]))

    def test_nonfinite_assertions_are_rejected(self):
        self.rejected(lambda p: p["cases"][0]["success_conditions"][0].update(equals=float("nan")))

    def test_json_pointer_escaping_and_array_indexes(self):
        self.assertEqual(resolve_pointer({"a/b": {"~": ["first", "second"]}}, "/a~1b/~0/1"), "second")

    def test_boolean_does_not_match_numeric_one(self):
        self.assertFalse(compare_conditions({"id": True}, [{"pointer": "/id", "equals": 1}])[0])

    def test_null_is_distinguished_from_missing(self):
        assertion = [{"pointer": "/value", "equals": None}]
        self.assertTrue(compare_conditions({"value": None}, assertion)[0])
        self.assertFalse(compare_conditions({}, assertion)[0])

    def test_default_ports_are_normalized(self):
        self.assertEqual(origin("https://EXAMPLE.COM"), origin("https://example.com:443"))

    def test_sensitive_proof_field_is_masked(self):
        _, proof = compare_conditions({"access_token": "x"}, [{"pointer": "/access_token", "equals": "x"}])
        self.assertEqual(proof[0]["observed"], "[redacted]")

    def test_zero_port_and_malformed_ipv6_origin_are_rejected(self):
        for url in ("http://example.test:0", "http://[invalid"):
            self.rejected(lambda p: p.update(base_url=url))

    def test_denial_assertions_must_be_a_list(self):
        self.rejected(lambda p: p["cases"][0].update(deny_conditions={}))
