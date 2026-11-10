# Financial capture UI — spec065 branch

Members with an explicit finance_private grant can open **Financial register** from Local records. The server independently enforces the current grant and record ownership; a technical administrator or another member with the same scope gains no access to your data. The existing session landing remains unchanged. No source, model, bank, lender or broker is contacted and no financial action or calculation is performed.

## Capture and correct

Choose **New financial record**, then goal, assumption, plan or source. Record a title/topic, explicit basis (confirmed input, assumption, forecast or unknown), calendar as-of date, source reference and optional target/source dates. Dates remain calendar dates. References are inert text/opaque identifiers, not fetched links. A confirmed input means your recording of it, not independent verification.

The amount starts unknown. Only **Record an amount** exposes a decimal string and currency. Zero is explicitly 0.00 with a currency; unknown remains null with no currency. The form mirrors server bounds and canonicalizes without floating-point arithmetic. Statement/source/title use printable single-line text; unsupported dates/currencies/versions reject rather than silently substituting. Historical target dates remain displayed, not inferred into future predictions.

Select a record to reread its current source, then correct it. Kind, owner and scope cannot be changed. Corrections preserve prior history and reset plan acceptance. A stale/conflicting or ambiguous response preserves the draft but disables further actions until **Discard draft and reload**. No mutation automatically retries or rebases onto unseen values. Unknown or malformed receipts never become editable data.

## Plan choice and history

A proposed plan needs an explicit **Acknowledge plan record only** checkbox before acceptance. This acknowledges the current record/revision only, stores owner/time and grants no execution permission. Any correction, read, page, format or navigation change withdraws UI confirmations. Review history explicitly; it is bounded to 25 revisions per page with a visible next-page control. Historical confirmations describe that version, not current authority to act.

## Copy and forget

Download the current list page, or the selected current record with one history page, only after reviewing scope and **Acknowledge financial copy limits**. JSON and Markdown use a fresh protected server export and strict owner/revision/history validation before creating a download. Markdown contains escaped JSON in an inert code block, so source strings cannot become remote-image or active HTML instructions. The file is an unmanaged copy, not a full backup or all history; inspect the next cursor and request other pages explicitly.

**Forget financial values** has its own acknowledgement. The server atomically scrubs current and historical payloads; the UI withdraws stale values/history and displays the minimal owner-only identity/type/version tombstone. Old downloads/screenshots/dumps/WAL remain outside this managed operation. Reading/exporting a tombstone/history cannot reintroduce financial values. No automatic deletion of backups occurs.

## Privacy and failures

Sensitive records, search/drafts and confirmations stay in memory only. They clear after at most 60 seconds from the current operation/new-draft deadline, on hidden tab, view/session/membership change or authority denial. The deadline is visible. Long or abort-ignoring requests cannot return into a new context or extend a timed-out view.401 returns to sign-in; other denials withdraw all data. No local storage, URL payload, telemetry, auto-refresh or auto-pagination. Ordinary errors expose sanitized status and require explicit reload before another mutation.

The list is one owner-scoped page of at most 25 rows, including disclosed tombstones; it is not a global total. Search is explicit, sent in protected POST bodies and scoped by the server. Record/history limits have clear errors; reads/exports/forgetting remain the server's supported paths at those limits. Navigation appears only for granted members and does not create or persist a grant.

## Evidence boundary

[PR19](https://github.com/LYF-FC/local-assistant-core/pull/19) merged the reviewed [server contract](FINANCIAL_REGISTER_API.md). [Spec065](../specs/065-financial-ui/spec.md) and [convergence](../specs/065-financial-ui/convergence.md) cover this open UI branch: strict client negatives and synthetic trusted HTTPS lifecycle/mobile/export/forget/conflict/late/hidden/expiry/denial evidence. No backend/schema/grant/fixture change is introduced, so no new native migration/restore claim is made.

The [dashboard](FEATURE_DASHBOARD.html) and [Markdown overview](FEATURE_OVERVIEW.md) now count merged FIN-06 server foundations as partial: 18 of the original 99 named features partial, 81 planned; 39 partial/116 planned across 155 references. The open UI branch is not a merged or complete financial feature. Full goal/progress modelling, imports/scenarios/portfolio/property research, whole-MVP/host acceptance and separately authorized private adoption remain open. Deferred REV/refactoring ordering remains unchanged.
