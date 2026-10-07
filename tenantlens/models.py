"""Strict, dependency-free project validation and JSON Pointer assertions."""

from __future__ import annotations

import copy
import math
import re
from urllib.parse import urlsplit, urlencode


class ValidationError(ValueError):
    pass


def text(value, label, maximum=240):
    if not isinstance(value, str) or not value.strip() or len(value) > maximum:
        raise ValidationError(f"{label}: expected a nonempty string (max {maximum}).")
    if any(ord(c) < 32 for c in value):
        raise ValidationError(f"{label}: control characters are not allowed.")
    return value


def identifier(value, label):
    value = text(value, label, 64)
    if not re.fullmatch(r"[a-zA-Z0-9_-]+", value):
        raise ValidationError(f"{label}: use letters, numbers, underscores or hyphens.")
    return value


def only_keys(obj, permitted, label):
    if not isinstance(obj, dict):
        raise ValidationError(f"{label}: expected an object.")
    if set(obj) - set(permitted):
        raise ValidationError(f"{label}: contains unsupported fields.")


def origin(url):
    text(url, "URL", 2048)
    try:
        parsed = urlsplit(url)
    except ValueError as exc:
        raise ValidationError("URL: malformed address.") from exc
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        raise ValidationError("URL: only absolute HTTP(S) URLs are supported.")
    if parsed.username is not None or parsed.password is not None:
        raise ValidationError("URL: embedded credentials are not allowed.")
    if "\\" in url or any(c.isspace() for c in url):
        raise ValidationError("URL: whitespace and backslashes are not allowed.")
    try:
        port = parsed.port if parsed.port is not None else (443 if parsed.scheme == "https" else 80)
    except ValueError as exc:
        raise ValidationError("URL: invalid port.") from exc
    if not 1 <= port <= 65535:
        raise ValidationError("URL: invalid port.")
    host = parsed.hostname.lower().encode("idna").decode("ascii")
    host = f"[{host}]" if ":" in host else host
    return f"{parsed.scheme}://{host}:{port}"


def relative_path(value):
    value = text(value, "path", 2048)
    try:
        parsed = urlsplit(value)
    except ValueError as exc:
        raise ValidationError("path: malformed relative path.") from exc
    if not value.startswith("/") or value.startswith("//") or parsed.scheme or parsed.netloc:
        raise ValidationError("path: expected an origin-relative path beginning with /.")
    if parsed.fragment or parsed.query or "\\" in value or any(c.isspace() for c in value):
        raise ValidationError("path: use the query object for parameters; fragments/whitespace are unsupported.")
    return value


def conditions(value, label):
    if not isinstance(value, list) or not 1 <= len(value) <= 20:
        raise ValidationError(f"{label}: define 1–20 JSON Pointer assertions.")
    result = []
    for item in value:
        only_keys(item, ("pointer", "equals"), label)
        pointer = item.get("pointer")
        if not isinstance(pointer, str) or len(pointer) > 256:
            raise ValidationError(f"{label}: invalid JSON Pointer.")
        if pointer and not pointer.startswith("/"):
            raise ValidationError(f"{label}: JSON Pointers begin with /.")
        if re.search(r"~(?![01])", pointer):
            raise ValidationError(f"{label}: invalid JSON Pointer escape.")
        if "equals" not in item:
            raise ValidationError(f"{label}: assertion is missing equals.")
        if isinstance(item["equals"], (dict, list)):
            raise ValidationError(f"{label}: assertions must compare scalar values.")
        if not isinstance(item["equals"], (str, int, float, bool, type(None))):
            raise ValidationError(f"{label}: unsupported assertion value.")
        if isinstance(item["equals"], float) and not math.isfinite(item["equals"]):
            raise ValidationError(f"{label}: assertion numbers must be finite.")
        if isinstance(item["equals"], str) and len(item["equals"]) > 1024:
            raise ValidationError(f"{label}: assertion value is too long.")
        result.append(copy.deepcopy(item))
    return result


def _bounded_number(value, label, low, high):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not low <= value <= high:
        raise ValidationError(f"{label}: expected a number between {low} and {high}.")
    return value


def validate_project(raw):
    only_keys(raw, ("schema_version", "id", "name", "base_url", "allowed_origins", "settings", "accounts", "cases"), "project")
    if type(raw.get("schema_version", 1)) is not int or raw.get("schema_version", 1) != 1:
        raise ValidationError("Unsupported schema_version.")
    project = {"schema_version": 1, "id": identifier(raw.get("id"), "project.id"), "name": text(raw.get("name"), "project.name")}
    base = text(raw.get("base_url"), "base_url", 2048).rstrip("/")
    base_origin = origin(base)
    parsed = urlsplit(base)
    if parsed.query or parsed.fragment or parsed.path not in ("", "/"):
        raise ValidationError("base_url: specify the origin only; put paths in each case.")
    project["base_url"] = base
    allowed = raw.get("allowed_origins", [base])
    if not isinstance(allowed, list) or not 1 <= len(allowed) <= 8:
        raise ValidationError("allowed_origins: expected 1–8 origins.")
    for entry in allowed:
        text(entry, "allowed_origins entry", 2048)
        origin(entry)
        p = urlsplit(entry)
        if p.path not in ("", "/") or p.query or p.fragment:
            raise ValidationError("allowed_origins: entries must be origins.")
    project["allowed_origins"] = sorted(set(origin(entry) for entry in allowed))
    if base_origin not in project["allowed_origins"]:
        raise ValidationError("base_url must be included in allowed_origins.")
    settings = raw.get("settings", {})
    only_keys(settings, ("timeout", "request_rate", "response_size_limit"), "settings")
    project["settings"] = {
        "timeout": _bounded_number(settings.get("timeout", 5), "timeout", 0.1, 30),
        "request_rate": _bounded_number(settings.get("request_rate", 12), "request_rate", 1, 50),
        "response_size_limit": int(_bounded_number(settings.get("response_size_limit", 262144), "response_size_limit", 1024, 1048576)),
    }
    accounts = raw.get("accounts")
    if not isinstance(accounts, list) or not 1 <= len(accounts) <= 12:
        raise ValidationError("accounts: expected 1–12 accounts.")
    project["accounts"] = []
    seen = set()
    for raw_account in accounts:
        only_keys(raw_account, ("id", "name", "tenant_id", "roles", "auth_env", "precheck"), "account")
        aid = identifier(raw_account.get("id"), "account.id")
        if aid in seen:
            raise ValidationError("account IDs must be unique.")
        seen.add(aid)
        env = text(raw_account.get("auth_env"), "auth_env", 128)
        if not re.fullmatch(r"TENANTLENS_[A-Z0-9_]+", env):
            raise ValidationError("auth_env: use a TENANTLENS_ prefixed environment variable.")
        roles = raw_account.get("roles", ["user"])
        if not isinstance(roles, list) or not 1 <= len(roles) <= 8:
            raise ValidationError("roles: expected 1–8 roles.")
        precheck = raw_account.get("precheck", {})
        only_keys(precheck, ("path", "conditions"), "precheck")
        project["accounts"].append({"id": aid, "name": text(raw_account.get("name"), "account.name"), "tenant_id": text(raw_account.get("tenant_id"), "tenant_id", 128), "roles": [text(r, "role", 64) for r in roles], "auth_env": env, "precheck": {"path": relative_path(precheck.get("path", "/api/whoami")), "conditions": conditions(precheck.get("conditions"), "precheck.conditions")}})
    cases = raw.get("cases")
    if not isinstance(cases, list) or not 1 <= len(cases) <= 50:
        raise ValidationError("cases: expected 1–50 cases.")
    project["cases"] = []
    case_ids = set()
    for c in cases:
        only_keys(c, ("id", "name", "resource_id", "tenant_id", "owner_account_id", "method", "path", "query", "baseline_account", "permissions", "success_conditions", "deny_statuses", "deny_conditions"), "case")
        cid = identifier(c.get("id"), "case.id")
        if cid in case_ids:
            raise ValidationError("case IDs must be unique.")
        case_ids.add(cid)
        if c.get("method", "GET") != "GET":
            raise ValidationError("v0.1 supports GET requests only.")
        baseline = c.get("baseline_account")
        permissions = c.get("permissions", {})
        if not isinstance(permissions, dict) or set(permissions) != seen or any(v not in ("allow", "deny") for v in permissions.values()):
            raise ValidationError("permissions: define allow/deny for every account exactly once.")
        if baseline not in seen or permissions[baseline] != "allow":
            raise ValidationError("baseline_account must reference an account with allow permission.")
        owner = c.get("owner_account_id", baseline)
        if owner not in seen:
            raise ValidationError("owner_account_id references an unknown account.")
        deny = c.get("deny_statuses", [403, 404])
        if not isinstance(deny, list) or any(type(s) is not int or s not in (400, 403, 404, 405, 409, 422) for s in deny):
            raise ValidationError("deny_statuses: supported values are 400, 403, 404, 405, 409, 422.")
        raw_deny = c.get("deny_conditions", [])
        if not isinstance(raw_deny, list):
            raise ValidationError("deny_conditions: expected an assertion list.")
        deny_conditions = conditions(raw_deny, "deny_conditions") if raw_deny else []
        query = c.get("query", {})
        if not isinstance(query, dict) or len(query) > 20:
            raise ValidationError("query: expected an object with at most 20 parameters.")
        for key, value in query.items():
            text(key, "query key", 100)
            text(value, "query value", 1024)
            if re.search(r"token|password|secret|api.?key|authorization", key, re.I):
                raise ValidationError("query: credentials must not be placed in URLs.")
        project["cases"].append({"id": cid, "name": text(c.get("name"), "case.name"), "resource_id": text(c.get("resource_id", cid), "resource_id", 128), "tenant_id": text(c.get("tenant_id"), "case.tenant_id", 128), "owner_account_id": owner, "method": "GET", "path": relative_path(c.get("path")), "query": copy.deepcopy(query), "baseline_account": baseline, "permissions": copy.deepcopy(permissions), "success_conditions": conditions(c.get("success_conditions"), "success_conditions"), "deny_statuses": sorted(set(deny)), "deny_conditions": deny_conditions})
    if len(project["accounts"]) * len(project["cases"]) > 300:
        raise ValidationError("A run supports at most 300 matrix checks.")
    return project


def request_path(case):
    query = urlencode(case.get("query", {}))
    return case["path"] + ("?" + query if query else "")


MISSING = object()


def resolve_pointer(data, pointer):
    if pointer == "":
        return data
    for segment in pointer[1:].split("/"):
        segment = segment.replace("~1", "/").replace("~0", "~")
        if isinstance(data, dict):
            data = data.get(segment, MISSING)
        elif isinstance(data, list) and re.fullmatch(r"0|[1-9][0-9]*", segment):
            index = int(segment)
            data = data[index] if index < len(data) else MISSING
        else:
            return MISSING
        if data is MISSING:
            break
    return data


def compare_conditions(data, assertions):
    evidence = []
    for assertion in assertions:
        value = resolve_pointer(data, assertion["pointer"]) if data is not None else MISSING
        expected = assertion["equals"]
        same_type = type(value) is type(expected) or (type(value) in (int, float) and type(expected) in (int, float))
        matched = value is not MISSING and same_type and value == expected
        # Store scalar proof fields, never arbitrary response bodies.
        observed = value if isinstance(value, (str, int, float, bool, type(None))) else "[non-scalar]"
        if value is MISSING:
            observed = "[missing]"
        if isinstance(observed, str):
            observed = observed[:1024]
        sensitive = bool(re.search(r"token|password|secret|api.?key|authorization|cookie", assertion["pointer"], re.I))
        evidence.append({"pointer": assertion["pointer"], "expected": "[redacted]" if sensitive else expected, "observed": "[redacted]" if sensitive else observed, "matched": matched})
    return bool(evidence) and all(e["matched"] for e in evidence), evidence
