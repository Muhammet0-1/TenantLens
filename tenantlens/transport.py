"""Bounded HTTP GET transport: verified TLS, explicit origin scope, no proxies/retries."""

from __future__ import annotations

from dataclasses import dataclass
import http.client
import json
import socket
import ssl
import time
from urllib.parse import urlsplit

from .models import origin, ValidationError


@dataclass
class Response:
    status: int | None = None
    data: object = None
    error: str | None = None
    elapsed_ms: int = 0


class HTTPTransport:
    def __init__(self, project):
        self.project = project

    def get(self, path, token):
        started = time.monotonic()
        connection = None
        try:
            url = self.project["base_url"] + path
            if origin(url) not in self.project["allowed_origins"]:
                return Response(error="scope_rejected")
            if any(c in token for c in ("\r", "\n")) or len(token) > 8192:
                return Response(error="invalid_credential")
            parsed = urlsplit(url)
            if parsed.scheme == "https":
                connection = http.client.HTTPSConnection(parsed.hostname, parsed.port or 443, timeout=self.project["settings"]["timeout"], context=ssl.create_default_context())
            else:
                connection = http.client.HTTPConnection(parsed.hostname, parsed.port or 80, timeout=self.project["settings"]["timeout"])
            destination = parsed.path + ("?" + parsed.query if parsed.query else "")
            # A new connection for every request: no shared cookie or credential state.
            connection.request("GET", destination, headers={"Authorization": "Bearer " + token, "Accept": "application/json", "User-Agent": "TenantLens/0.1", "Connection": "close", "Accept-Encoding": "identity"})
            # Keep a socket reference even when getresponse detaches a closing connection.
            wire_socket = connection.sock
            remaining = self.project["settings"]["timeout"] - (time.monotonic() - started)
            if remaining <= 0:
                raise TimeoutError
            wire_socket.settimeout(remaining)
            response = connection.getresponse()
            status = response.status
            maximum = self.project["settings"]["response_size_limit"]
            chunks = []
            count = 0
            deadline = started + self.project["settings"]["timeout"]
            while count <= maximum:
                if response.isclosed():
                    break
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise TimeoutError
                wire_socket.settimeout(remaining)
                part = response.read1(min(65536, maximum + 1 - count))
                if not part:
                    break
                chunks.append(part)
                count += len(part)
            if count > maximum:
                return Response(status=status, error="response_too_large")
            raw = b"".join(chunks)
            content_type = response.getheader("Content-Type", "").split(";")[0].lower()
            data = None
            if content_type == "application/json" or content_type.endswith("+json"):
                try:
                    data = json.loads(raw.decode("utf-8"), parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))
                except (UnicodeError, ValueError, RecursionError):
                    pass
            return Response(status=status, data=data, elapsed_ms=int((time.monotonic() - started) * 1000))
        except (TimeoutError, socket.timeout):
            return Response(error="timeout")
        except (OSError, http.client.HTTPException, ValueError, ValidationError):
            # Exception strings can contain target data; persist a fixed reason code only.
            return Response(error="connection_failed")
        finally:
            if connection is not None:
                connection.close()
