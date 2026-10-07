from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import time
import shutil
import ssl
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from tenantlens.demo import demo_project
from tenantlens.models import validate_project
from tenantlens.transport import HTTPTransport
from helpers import running


class Transport(unittest.TestCase):
    def setUp(self):
        self.seen = []
        seen = self.seen
        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *_):
                pass
            def do_GET(self):
                seen.append((self.path, dict(self.headers)))
                status, mime, body = 200, "application/json", b'{"id":"ok"}'
                if self.path == "/redirect":
                    status = 302
                elif self.path == "/html":
                    mime, body = "text/html", b'<html>sign in</html>'
                elif self.path == "/large":
                    body = b'x' * 2048
                elif self.path == "/invalid":
                    body = b'{"id": NaN}'
                elif self.path == "/slow":
                    time.sleep(0.3)
                self.send_response(status)
                self.send_header("Content-Type", mime)
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Set-Cookie", "session=must-not-reuse")
                if status == 302:
                    self.send_header("Location", "/followed")
                self.end_headers()
                try:
                    self.wfile.write(body)
                except (BrokenPipeError, ConnectionResetError):
                    pass
        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        server.daemon_threads = True
        self.context = running(server)
        url = self.context.__enter__()
        self.addCleanup(self.context.__exit__, None, None, None)
        self.project = validate_project(demo_project(base_url=url))
        self.transport = HTTPTransport(self.project)

    def test_redirect_is_returned_without_following(self):
        self.assertEqual(self.transport.get("/redirect", "first").status, 302)
        self.assertEqual(len(self.seen), 1)

    def test_separate_accounts_do_not_share_cookies_or_tokens(self):
        self.transport.get("/one", "first")
        self.transport.get("/two", "second")
        self.assertEqual([h["Authorization"] for _, h in self.seen], ["Bearer first", "Bearer second"])
        self.assertTrue(all("Cookie" not in h for _, h in self.seen))

    def test_html_login_page_produces_no_json_proof(self):
        self.assertIsNone(self.transport.get("/html", "t").data)

    def test_response_size_limit_is_enforced(self):
        self.project["settings"]["response_size_limit"] = 1024
        self.assertEqual(self.transport.get("/large", "t").error, "response_too_large")

    def test_timeout_is_enforced(self):
        self.project["settings"]["timeout"] = 0.1
        start = time.monotonic()
        self.assertEqual(self.transport.get("/slow", "t").error, "timeout")
        self.assertLess(time.monotonic() - start, 0.25)

    def test_scope_rejection_performs_no_http_request(self):
        self.project["allowed_origins"] = ["https://other.test:443"]
        self.assertEqual(self.transport.get("/one", "t").error, "scope_rejected")
        self.assertEqual(self.seen, [])

    def test_header_injection_is_rejected(self):
        self.assertEqual(self.transport.get("/one", "t\r\nX-Evil: yes").error, "invalid_credential")
        self.assertEqual(self.seen, [])

    def test_proxy_environment_does_not_redirect_credentials(self):
        with patch.dict("os.environ", {"HTTP_PROXY": "http://127.0.0.1:1", "HTTPS_PROXY": "http://127.0.0.1:1"}):
            self.assertEqual(self.transport.get("/one", "t").status, 200)

    def test_nonstandard_json_numbers_cannot_enter_evidence(self):
        self.assertIsNone(self.transport.get("/invalid", "t").data)

    @unittest.skipUnless(shutil.which("openssl"), "openssl is required to generate a temporary self-signed fixture")
    def test_untrusted_tls_certificate_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            key, certificate = directory + "/key.pem", directory + "/certificate.pem"
            subprocess.run(["openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes", "-keyout", key, "-out", certificate, "-days", "1", "-subj", "/CN=localhost"], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            server = ThreadingHTTPServer(("127.0.0.1", 0), BaseHTTPRequestHandler)
            context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
            context.load_cert_chain(certificate, key)
            server.socket = context.wrap_socket(server.socket, server_side=True)
            with running(server) as http_url:
                project = validate_project(demo_project(base_url=http_url.replace("http:", "https:")))
                self.assertEqual(HTTPTransport(project).get("/", "t").error, "connection_failed")
