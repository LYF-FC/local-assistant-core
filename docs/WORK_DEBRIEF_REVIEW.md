# Synthetic text debrief review — spec 027

The optional Work notes screen can prepare reviewable proposals from explicitly labelled sample lines. It uses a deterministic browser parser and the existing draft editor/capture/recovery/confirmation flow. It does not interpret arbitrary prose, infer assignments, record audio, run a model or execute actions. Full spec 005 and independent recovery acceptance remain open.

## Use the sample flow

Use the existing optional complete-interface setup in WORK_NOTES_INTERFACE.md; no new flag, migration, provisioning or credential is needed. Standard setup remains disabled. Load the currently assigned synthetic workspace, open notes, then choose **New sample debrief**. Enter up to ten lines such as:

```text
Observation: Sample service is ready
Action: Prepare the sample agenda
Decision: Keep the sample review
Question: Clarify the sample dependency
```

Choose **Prepare proposals**. This step sends no network request and saves nothing. Review the exact original line beside each proposal. Unsupported lines fail the entire preparation with a line-specific message; none are silently dropped or truncated. Duplicate wording on different lines stays separate. Omit an unrequested proposal explicitly, or discard the whole debrief.

Choose **Review line** to open the existing editor. The proposal's text/type are prefilled; changing them does not change the original quote. Owner/date start Unknown even when a name/date appears in the text. Explicitly choose registered sources, a retention policy and expiry, then request a draft save. Only that reviewed item is submitted; there is no batch save. Saving a decision or action still creates a draft, not a commitment or execution.

A proposal is marked awaiting processing until a matching original capture nonce is reported applied. Uncertain responses keep the existing same-request retry/recovery path and block another save. Historical results for other nonces cannot label another proposal as saved. Deliberately apply the request with the existing trusted local capture executor; then inspect and separately confirm its exact version. Worker denial requires deliberate re-review. Existing APIs recheck current user/session/workspace/source/policy/retention; client preparation confers no authority.

## Source and retention limits

Input is at most 3000 ASCII characters and ten nonblank lines, with 1–246 sample-text characters after each supported label. Labels are case-insensitive, and blank lines/CRLF are supported. Text after the label uses letters, numbers, spaces, dots, underscores or hyphens. Original quote whitespace and line numbers are preserved for review; no instruction in that text runs as code or an action.

Original lines are temporary review aids, not durable source records. Choosing a registered sample source is an explicit reference selection; it does not register or verify this debrief as that source. Only the reviewed note body and selected existing source IDs reach the capture API. Raw debrief text, quotes and line references are not implicitly stored, exported or audited as transcript provenance. Durable transcript/source lineage, arbitrary prose extraction and voice remain later work.

The debrief shares the existing catalogue's at-most-60-second validity. Reload, expiry, workspace/view/sign-out, access denial or unavailable private storage clears input, proposals, editor seeds and frozen payloads. Discard clears those debrief copies while preserving only minimal existing request metadata; an already submitted request can still apply and must be reconciled. Forgetting a note also discards the in-screen debrief before submitting its forget request, so the screen does not retain its original quote. Browser data has no local/session storage, URL, download, log, shared cache or external-model path.

## Verification and next work

Parser tests exercise bounds, exact source lines, malformed later lines, duplicates, inert instruction-like wording and nonce-bound outcomes. Optional actual verified-TLS browser tests exercise two separately reviewed saves, unknowns, manual application/confirmation, omission, ambiguity recovery, discard and expiry/denial/navigation cleanup, with mobile/desktop screenshots. Existing backend/security/PostgreSQL/logical-restore CI remains required on the exact review head.

Next: remaining source/export/retention and independent key/derived-copy/old-backup/full-host recovery acceptance. Real employer sources, inference, work connectors and full debrief-agent acceptance remain gated.
