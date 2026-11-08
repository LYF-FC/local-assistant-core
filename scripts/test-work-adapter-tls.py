"""Real verified local TLS probe of the explicit synthetic adapter overlay."""

import http.cookiejar
import json
import os
import ssl
import subprocess
import sys
import urllib.error
import urllib.request
from uuid import UUID, uuid4

assert os.environ["BUTLER_ENV"] == "test"
origin = os.environ["BUTLER_E2E_ORIGIN"]
assert origin == "https://localhost:18443"
context = ssl.create_default_context(cafile=os.environ["BUTLER_CI_CA_FILE"])
client = urllib.request.build_opener(
    urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()),
    urllib.request.HTTPSHandler(context=context),
)


def call(path, body=None, csrf=None):
    headers = {"Origin": origin, "Content-Type": "application/json"}
    if csrf:
        headers["X-CSRF-Token"] = csrf
    request = urllib.request.Request(origin + path, data=json.dumps(body).encode() if body is not None else None, headers=headers)
    try:
        response = client.open(request, timeout=15)
    except urllib.error.HTTPError as error:
        response = error
    with response:
        return response.status, json.load(response)


status, auth = call("/api/v1/auth/login", {"slug": "browser-work-owner", "password": "synthetic-browser-password-only-0123456789"})
assert status == 200, "Synthetic adapter TLS login failed"
status, registry = call("/api/v1/work/workspaces")
assert status == 200
identifier = next(w["id"] for w in registry["items"] if w["slug"] == "synthetic-adapter-ci")
status, result = call(f"/api/v1/work/workspaces/{identifier}/validation-read", {"limit": 2}, auth["csrf_token"])
if sys.argv[1] == "present":
    assert status == 200, "Opt-in synthetic TLS read failed"
    assert [row["marker"] for row in result["items"]] == ["synthetic:container-adapter"]
    assert result["ingestion_allowed"] is False and result["model_invoked"] is False
else:
    assert status == 503 and "items" not in result, "Removed credential file did not fail closed"
draft = str(UUID(os.environ["BUTLER_CI_REVIEW_DRAFT"]))
prefix = f"/api/v1/work/workspaces/{identifier}/drafts/{draft}"
status, preview = call(prefix+"/preview", {}, auth["csrf_token"])
review = {"expected_revision": 1,"reviewed_hash": preview.get("payload_hash","0"*64),"request_id":str(uuid4()),"decision":"approve"}
if sys.argv[1] == "present":
    assert status == 200 and preview["item"]["marker"] == "synthetic:tls-review"
    status, acknowledgement = call(prefix+"/review", review, auth["csrf_token"])
    assert status == 200 and acknowledgement["confirmation_applied"] is False
    assert acknowledgement["execution_allowed"] is False
    status, repeated = call(prefix+"/review", review, auth["csrf_token"])
    assert status == 200 and repeated["replayed"] is True
    assert repeated["review_preparation_id"] == acknowledgement["review_preparation_id"]
    status, pending = call(prefix+"/confirm", {"review_preparation_id":acknowledgement["review_preparation_id"],"expected_revision":1,"request_id":str(uuid4()),"decision":"confirm_note"}, auth["csrf_token"])
    assert status == 202 and pending["confirmation_applied"] is False
    command = str(UUID(pending["confirmation_request_id"]))
    subprocess.run(["docker","compose","-f","infra/core/compose.yml","run","--rm","-T","migrate","python","-m","app.work_confirmation_worker","--environment","test","--request",command], check=True, capture_output=True, timeout=45)
    status, applied = call(f"/api/v1/work/workspaces/{identifier}/confirmations/{command}/status", {}, auth["csrf_token"])
    assert status == 200 and applied["state"] == "applied" and applied["applied_revision"] == 2
    assert applied["execution_allowed"] is False
    status, bundle = call(f"/api/v1/work/workspaces/{identifier}/context/preview", {"selections":[{"id":draft,"expected_revision":2}]}, auth["csrf_token"])
    assert status == 200 and bundle["items"][0]["marker"] == "synthetic:tls-review"
    assert bundle["reference_only"] is True and bundle["model_invoked"] is False
    assert bundle["execution_allowed"] is False
    status, stale = call(f"/api/v1/work/workspaces/{identifier}/context/preview", {"selections":[{"id":draft,"expected_revision":1}]}, auth["csrf_token"])
    assert status == 409 and "items" not in stale
    capture_body = {"request_id":str(uuid4()),"decision":"capture_draft","policy_id":preview["item"]["policy_id"],"draft":{"kind":"question","marker":"synthetic:tls-captured","source_ids":preview["item"]["source_ids"],"retain_until":preview["item"]["retain_until"]}}
    status, prepared = call(f"/api/v1/work/workspaces/{identifier}/captures",capture_body,auth["csrf_token"])
    assert status == 202 and prepared["capture_applied"] is False
    capture_command = str(UUID(prepared["capture_preparation_id"]))
    subprocess.run(["docker","compose","-f","infra/core/compose.yml","run","--rm","-T","migrate","python","-m","app.work_capture_worker","--environment","test","--request",capture_command],check=True,capture_output=True,timeout=45)
    status, saved = call(f"/api/v1/work/workspaces/{identifier}/captures/{capture_command}/status",{},auth["csrf_token"])
    assert status == 200 and saved["capture_applied"] is True and saved["confirmation_applied"] is False
    captured_id = str(UUID(saved["record_id"]))
    status, captured = call(f"/api/v1/work/workspaces/{identifier}/drafts/{captured_id}/preview",{},auth["csrf_token"])
    assert status == 200 and captured["item"]["marker"] == "synthetic:tls-captured" and captured["item"]["owner_id"] is None
    change_body = {"request_id":str(uuid4()),"decision":"correct_note","expected_revision":1,"draft":dict(capture_body["draft"],marker="synthetic:tls-corrected")}
    status, change = call(f"/api/v1/work/workspaces/{identifier}/drafts/{captured_id}/correct",change_body,auth["csrf_token"])
    assert status == 202
    change_id = str(UUID(change["change_request_id"]))
    subprocess.run(["docker","compose","-f","infra/core/compose.yml","run","--rm","-T","migrate","python","-m","app.work_notes_worker","--environment","test","--request",change_id],check=True,capture_output=True,timeout=45)
    status, changed = call(f"/api/v1/work/workspaces/{identifier}/note-changes/{change_id}/status",{},auth["csrf_token"])
    assert status == 200 and changed["change_applied"] is True and changed["revision"] == 2
    status, updated = call(f"/api/v1/work/workspaces/{identifier}/drafts/{captured_id}/preview",{},auth["csrf_token"])
    assert status == 200 and updated["item"]["marker"] == "synthetic:tls-corrected"
    status, forget = call(f"/api/v1/work/workspaces/{identifier}/drafts/{captured_id}/forget",{"request_id":str(uuid4()),"decision":"forget_note","expected_revision":2},auth["csrf_token"])
    assert status == 202
    forget_id = str(UUID(forget["change_request_id"]))
    subprocess.run(["docker","compose","-f","infra/core/compose.yml","run","--rm","-T","migrate","python","-m","app.work_notes_worker","--environment","test","--request",forget_id],check=True,capture_output=True,timeout=45)
    status, forgotten = call(f"/api/v1/work/workspaces/{identifier}/note-changes/{forget_id}/status",{},auth["csrf_token"])
    assert status == 200 and forgotten["change_applied"] is True and forgotten["revision"] == 3
    status, hidden = call(f"/api/v1/work/workspaces/{identifier}/drafts/{captured_id}/preview",{},auth["csrf_token"])
    assert status == 404 and "item" not in hidden
    print("Explicit synthetic correction → local apply → forget TLS probe passed")
    print("Explicit synthetic capture → local save → draft preview TLS probe passed")
    print("Explicit synthetic one-time confirmation and selected context TLS probe passed")
else:
    assert status == 503 and "item" not in preview
    status, denied = call(prefix+"/review",review,auth["csrf_token"])
    assert status == 503 and "review_preparation_id" not in denied
    status, denied = call(f"/api/v1/work/workspaces/{identifier}/context/preview", {"selections":[{"id":draft,"expected_revision":2}]}, auth["csrf_token"])
    assert status == 503 and "items" not in denied
    status, denied = call(f"/api/v1/work/workspaces/{identifier}/captures",{"request_id":str(uuid4()),"decision":"capture_draft","policy_id":str(uuid4()),"draft":{"kind":"question","marker":"synthetic:missing-secret","source_ids":[str(uuid4())],"retain_until":"2099-01-01T00:00:00+00:00"}},auth["csrf_token"])
    assert status == 503 and "capture_preparation_id" not in denied
    status, denied = call(f"/api/v1/work/workspaces/{identifier}/notes/export", {"purpose":"preview","selections":[{"id":draft,"expected_revision":2}]}, auth["csrf_token"])
    assert status == 503 and "bundle" not in denied
    print("Synthetic export missing-credential TLS denial passed")
print("Explicit synthetic draft review/context TLS probe passed: " + sys.argv[1])
print("Explicit synthetic adapter TLS probe passed: " + sys.argv[1])
