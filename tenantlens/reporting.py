"""Escaped, standalone reports; no response bodies or credential headers."""

from __future__ import annotations

import html
import json


def json_report(run):
    return json.dumps(run, ensure_ascii=False, indent=2, allow_nan=False).encode("utf-8")


def html_report(run):
    esc = lambda value: html.escape(str(value), quote=True)
    rows = []
    for item in run.get("results", []):
        evidence = json.dumps(item["evidence"], ensure_ascii=False, indent=2)
        rows.append("<tr><td>" + esc(item["case_name"]) + "<br><code>" + esc(item["path"]) + "</code></td><td>" + esc(item["account_name"]) + "</td><td>" + esc(item["expected"]) + "</td><td class='" + esc(item["verdict"]) + "'>" + esc(item["verdict"]) + "</td><td>" + esc(item["observed_status"] or "—") + "</td><td>" + esc(item["reason"]) + "<br><code>" + esc(item["reason_code"]) + "</code><details><summary>Evidence</summary><p>Identity verified: " + esc(item["identity_verified"]) + "; baseline verified: " + esc(item["baseline_verified"]) + "</p><pre>" + esc(evidence) + "</pre></details></td></tr>")
    counts = " · ".join(f"{esc(key)}: {esc(value)}" for key, value in run["counts"].items())
    document = """<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'; base-uri 'none'"><title>TenantLens report</title><style>body{font:14px/1.6 system-ui,sans-serif;color:#18263c;background:#f7f9fc;margin:0;padding:32px}main{max-width:1200px;margin:auto}h1{font-size:28px}table{width:100%;border-collapse:collapse;background:white}td,th{padding:12px;border-bottom:1px solid #dce3ec;text-align:left;vertical-align:top}th{background:#eaf0f7}code,pre{font:12px/1.5 monospace;white-space:pre-wrap;overflow-wrap:anywhere}pre{max-width:480px}.VIOLATION{color:#a52d44;font-weight:bold}.PASS{color:#16634a}.INCONCLUSIVE{color:#825813}.ERROR{color:#a52d44}.scope{color:#52637c;margin:24px 0}.table{overflow:auto}a{color:#254e84}@media(max-width:640px){body{padding:14px}}</style><main>"""
    document += "<h1>TenantLens · " + esc(run["project_name"]) + "</h1><p>Run: " + esc(run["id"]) + "<br>Started: " + esc(run["started_at"]) + "<br>Status: " + esc(run["status"]) + "</p><p>" + counts + "</p><p class='scope'>Results apply only to the configured accounts, resources and assertions at the time of this run. PASS means the defined expectation was met; it is not a general security certification. Identity prechecks and resource baselines are required. Raw response bodies and credential headers are not included.</p><div class='table'><table><thead><tr><th>Case</th><th>Account</th><th>Expected</th><th>Verdict</th><th>HTTP</th><th>Reason / proof</th></tr></thead><tbody>" + "".join(rows) + "</tbody></table></div></main></html>"
    auxiliary = json.dumps({"identities": run.get("identities", {}), "baselines": run.get("baselines", {})}, ensure_ascii=False, indent=2)
    document = document.replace("</main></html>", "<h2>Identity checks and positive baselines</h2><p>HTTP requests: " + esc(run.get("request_count", 0)) + "; finished: " + esc(run.get("finished_at") or "—") + "</p><details><summary>Verification evidence</summary><pre>" + esc(auxiliary) + "</pre></details></main></html>")
    return document.encode("utf-8")
