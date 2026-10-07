"""Authorization decisions based on identity checks, positive baselines and proof."""

from __future__ import annotations

import copy
from datetime import datetime, timezone
import os
import threading
import time
from urllib.parse import quote, quote_plus
from uuid import uuid4

from .models import validate_project, compare_conditions, request_path
from .transport import HTTPTransport, Response


REASONS = {
    "allowed_access": "İzinli erişimde başarı kanıtı doğrulandı.",
    "denied_access": "Geçerli hesap ve baseline ile beklenen erişim reddi doğrulandı.",
    "unexpected_access": "Yasak erişimde başarı kanıtı doğrulandı: izin sınırı ihlali.",
    "expected_allow_denied": "İzinli olması beklenen erişim açıkça reddedildi; politika beklentisi ihlali.",
    "identity_unverified": "Hesap kimliği veya şirket bilgisi doğrulanamadı.",
    "baseline_unverified": "İzinli baseline doğrulanamadığı için kaynak karşılaştırması belirsiz.",
    "missing_credential": "Hesabın ortam değişkeni eksik veya geçersiz.",
    "session_rejected": "Oturum bu istek sırasında reddedildi; erişim politikası değerlendirilemedi.",
    "insufficient_evidence": "Yanıt, tanımlanan başarı veya ret koşullarını karşılamıyor.",
    "conflicting_evidence": "Başarı ve ret koşulları çelişiyor; koşulları gözden geçirin.",
    "redirect": "Yönlendirme takip edilmedi; erişim sonucu belirsiz.",
    "server_error": "Hedef sunucu hata döndürdü; bu bir erişim reddi kanıtı değil.",
    "timeout": "İstek zaman sınırını aştı.",
    "connection_failed": "Hedefe bağlantı kurulamadı veya HTTP yanıtı okunamadı.",
    "response_too_large": "Yanıt, yapılandırılmış boyut sınırını aştı.",
    "scope_rejected": "İstek, yapılandırılmış origin kapsamı dışında.",
    "invalid_credential": "Kimlik bilgisi biçimi geçersiz.",
    "run_cancelled": "Çalıştırma kullanıcı tarafından durduruldu.",
}


def utcnow():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Redactor:
    def __init__(self, secrets):
        variants = set()
        for secret in secrets:
            if secret:
                variants.update((secret, quote(secret, safe=""), quote_plus(secret)))
        self.secrets = sorted(variants, key=len, reverse=True)

    def clean(self, value):
        if isinstance(value, str):
            for secret in self.secrets:
                value = value.replace(secret, "[redacted]")
            return value
        if isinstance(value, list):
            return [self.clean(item) for item in value]
        if isinstance(value, dict):
            return {self.clean(k): self.clean(v) for k, v in value.items()}
        return value


def environment_secrets():
    controls = {"TENANTLENS_TEST_PORT", "TENANTLENS_CHROMIUM", "TENANTLENS_BROWSER_ARGS"}
    return [value for key, value in os.environ.items() if key.startswith("TENANTLENS_") and key not in controls and value]


def evaluate(case, expected, response):
    success, evidence = compare_conditions(response.data, case["success_conditions"])
    success = success and response.status is not None and 200 <= response.status < 300
    deny_json = compare_conditions(response.data, case["deny_conditions"])[0] if case["deny_conditions"] else False
    denied = response.status in case["deny_statuses"] or (deny_json and response.status is not None and 200 <= response.status < 300)
    if response.error:
        return "ERROR", response.error, evidence
    if response.status == 401:
        return "INCONCLUSIVE", "session_rejected", evidence
    if response.status is not None and response.status >= 500:
        return "ERROR", "server_error", evidence
    if response.status is not None and 300 <= response.status < 400:
        return "INCONCLUSIVE", "redirect", evidence
    if success and denied:
        return "INCONCLUSIVE", "conflicting_evidence", evidence
    if success:
        return ("PASS", "allowed_access", evidence) if expected == "allow" else ("VIOLATION", "unexpected_access", evidence)
    if denied:
        return ("PASS", "denied_access", evidence) if expected == "deny" else ("VIOLATION", "expected_allow_denied", evidence)
    return "INCONCLUSIVE", "insufficient_evidence", evidence


def run_project(raw, *, transport=None, credentials=None, cancel=None, progress=None, sleeper=time.sleep, run_id=None):
    project = validate_project(raw)
    accounts = {a["id"]: a for a in project["accounts"]}
    tokens = {aid: (credentials.get(a["auth_env"], "") if credentials is not None else os.environ.get(a["auth_env"], "")) for aid, a in accounts.items()}
    redactor = Redactor(list(tokens.values()))
    transport = transport or HTTPTransport(project)
    cancel = cancel or threading.Event()
    total = len(project["cases"]) * len(accounts)
    result = {"id": run_id or uuid4().hex, "project_id": project["id"], "project_name": project["name"], "started_at": utcnow(), "finished_at": None, "status": "running", "total": total, "completed": 0, "request_count": 0, "project": copy.deepcopy(project), "identities": {}, "baselines": {}, "results": [], "counts": {k: 0 for k in ("PASS", "VIOLATION", "INCONCLUSIVE", "ERROR")}}
    last_request = None

    def publish():
        if progress:
            progress(redactor.clean(copy.deepcopy(result)))

    def request(path, aid):
        nonlocal last_request
        if cancel.is_set():
            return Response(error="run_cancelled")
        if last_request is not None:
            delay = max(0, 1 / project["settings"]["request_rate"] - (time.monotonic() - last_request))
            if delay:
                sleeper(delay)
        if cancel.is_set():
            return Response(error="run_cancelled")
        last_request = time.monotonic()
        result["request_count"] += 1
        return transport.get(path, tokens[aid])

    for aid, account in accounts.items():
        token = tokens[aid]
        if not token or len(token) > 8192 or any(c in token for c in "\r\n"):
            result["identities"][aid] = {"verified": False, "reason_code": "missing_credential", "status": None, "evidence": []}
            continue
        response = request(account["precheck"]["path"], aid)
        matched, evidence = compare_conditions(response.data, account["precheck"]["conditions"])
        valid = not response.error and response.status is not None and 200 <= response.status < 300 and matched
        result["identities"][aid] = {"verified": valid, "reason_code": "verified" if valid else response.error or "identity_unverified", "status": response.status, "evidence": evidence}
        publish()
    for case in project["cases"]:
        aid = case["baseline_account"]
        if not result["identities"][aid]["verified"]:
            result["baselines"][case["id"]] = {"verified": False, "status": None, "reason_code": "identity_unverified", "evidence": []}
            continue
        response = request(request_path(case), aid)
        matched, evidence = compare_conditions(response.data, case["success_conditions"])
        denial = compare_conditions(response.data, case["deny_conditions"])[0] if case["deny_conditions"] else False
        valid = not response.error and response.status is not None and 200 <= response.status < 300 and matched and not denial
        result["baselines"][case["id"]] = {"verified": valid, "status": response.status, "reason_code": "verified" if valid else response.error or "baseline_unverified", "evidence": evidence}
        publish()
    for case in project["cases"]:
        for aid in accounts:
            response = Response()
            evidence = []
            if cancel.is_set():
                verdict, reason = "INCONCLUSIVE", "run_cancelled"
            elif not result["identities"][aid]["verified"]:
                verdict, reason = "INCONCLUSIVE", result["identities"][aid]["reason_code"]
            elif not result["baselines"][case["id"]]["verified"]:
                verdict, reason = "INCONCLUSIVE", "baseline_unverified"
            else:
                response = request(request_path(case), aid)
                verdict, reason, evidence = evaluate(case, case["permissions"][aid], response)
                if reason == "run_cancelled":
                    verdict = "INCONCLUSIVE"
            record = {"case_id": case["id"], "case_name": case["name"], "account_id": aid, "account_name": accounts[aid]["name"], "tenant_id": accounts[aid]["tenant_id"], "resource_tenant_id": case["tenant_id"], "expected": case["permissions"][aid], "method": "GET", "path": case["path"], "verdict": verdict, "reason_code": reason, "reason": REASONS.get(reason, "Kontrol tamamlanamadı."), "observed_status": response.status, "elapsed_ms": response.elapsed_ms, "evidence": evidence, "identity_verified": result["identities"][aid]["verified"], "baseline_verified": result["baselines"][case["id"]]["verified"]}
            result["results"].append(record)
            result["counts"][verdict] += 1
            result["completed"] += 1
            publish()
    result["finished_at"] = utcnow()
    result["status"] = "cancelled" if cancel.is_set() else "completed"
    publish()
    return redactor.clean(result)
