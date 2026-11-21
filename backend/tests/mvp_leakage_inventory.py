"""Route inventory for the whole-MVP leakage suite (Gate 1): every registered operation, exactly one
classification. Executable and kept next to the tests; it is not a status register.

* ``swept``: exercised by ``mvp_leakage_support`` through the named adapter operation, in
  ``test_mvp_leakage.py::test_sweep[<adapter>]`` (SQLite) and
  ``integration/test_mvp_leakage_postgres.py::test_sweep[<adapter>]`` (restricted role).
  ``test_mvp_leakage.py::test_every_swept_route_was_requested`` checks, from the requests really made,
  that a swept route was called.
* ``credited``: covered by existing tests named exactly (file and function); the note says what they
  establish and where they are weaker than this suite.
* ``excluded``: not covered here, with the reason. Reasons that begin ``uncovered limitation`` name a
  gap this batch did not close.

The Work module is excluded as a whole: it has its own authority suites (listed below).
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Entry:
    kind: str
    adapter: str = ""
    what: str = ""
    tests: tuple = ()
    reason: str = ""


def swept(adapter, what):
    return Entry("swept", adapter=adapter, what=what)


def credited(reason, *tests):
    return Entry("credited", tests=tests, reason=reason)


def excluded(reason):
    return Entry("excluded", reason=reason)


AUTH_PREFIX = "/api/v1/auth/"  # authentication routes: out of this suite's scope by definition

WORK_SUITES = (
    "test_work_access.py",
    "test_work_authority.py",
    "test_work_lifecycle.py",
    "integration/test_work_authority_postgres.py",
    "integration/test_work_read_postgres.py",
    "integration/test_work_drafts_postgres.py",
)
WORK_REASON = (
    "the Work module has its own authority suites ("
    + ", ".join(WORK_SUITES)
    + "), its own roles and brokered reads; it is outside this sweep's household actor model"
)

DOCS_ISO = "test_documents_isolation.py"
DOCS_ISO_PG = "integration/test_documents_isolation_postgres.py"


def docs_tests(*names):
    return tuple(f"{DOCS_ISO}::{n}" for n in names) + tuple(f"{DOCS_ISO_PG}::{n}" for n in names)


ENTRIES = {}


def add(method, path, entry):
    assert (method, path) not in ENTRIES, (method, path)
    ENTRIES[(method, path)] = entry


def group(prefix, rows):
    for method, tail, entry in rows:
        add(method, prefix + tail, entry)


group(
    "/api/v1/approvals",
    [
        ("POST", "", swept("approvals", "create")),
        ("POST", "/query", swept("approvals", "listing")),
        ("GET", "/{identifier}", swept("approvals", "read")),
        ("POST", "/{identifier}/cancel", swept("approvals", "mutation:cancel")),
        ("POST", "/{identifier}/consume", swept("approvals", "mutation:consume")),
        ("POST", "/{identifier}/decide", swept("approvals", "mutation:decide")),
    ],
)
group(
    "/api/v1/calendars",
    [
        ("POST", "", swept("calendars", "create")),
        ("POST", "/briefing", swept("calendars", "view:briefing")),
        ("POST", "/query", swept("calendars", "listing")),
        ("POST", "/{identifier}/export", swept("calendars", "export_one")),
        ("POST", "/{identifier}/forget", swept("calendars", "mutation:forget")),
        ("POST", "/{identifier}/history", swept("calendars", "history")),
        ("POST", "/{identifier}/import", swept("calendars", "mutation:import")),
        ("POST", "/{identifier}/read", swept("calendars", "read")),
        ("POST", "/{identifier}/unavailable", swept("calendars", "mutation:unavailable")),
        (
            "POST",
            "/{identifier}/provider",
            excluded(
                "uncovered limitation: a hidden (not in the OpenAPI schema) owner route that needs the synthetic "
                "provider fixture world; existing tests call it with a missing id only "
                "(test_calendar_briefing_v2.py, the 404 uniformity test) and as the owner"
            ),
        ),
        (
            "POST",
            "/{identifier}/sync",
            excluded(
                "uncovered limitation: hidden owner route that needs a declared provider and the synthetic "
                "provider fixture world; no test makes a foreign-actor call"
            ),
        ),
        (
            "POST",
            "/{identifier}/sync-status",
            excluded(
                "uncovered limitation: hidden owner route that needs a declared provider and the synthetic "
                "provider fixture world; no test makes a foreign-actor call"
            ),
        ),
    ],
)
group(
    "/api/v1/context",
    [
        ("GET", "/candidates", swept("context", "listing")),
        ("POST", "/preview", swept("context", "read")),
    ],
)
group(
    "/api/v1/discovery",
    [
        ("POST", "", swept("discovery", "create")),
        ("GET", "", swept("discovery", "listing")),
        ("GET", "/{identifier}", swept("discovery", "read")),
        ("PUT", "/{identifier}/details", swept("discovery", "mutation:details")),
        ("PUT", "/{identifier}/feedback", swept("discovery", "mutation:feedback")),
        ("POST", "/inbox", swept("discovery", "view:inbox")),
        (
            "POST",
            "/ideas",
            credited(
                "asserts 401/403 for no session, scope and CSRF, a foreign idea refused with 404 for a holder of "
                "the same private scope and for a revoked grant; seeds one idea only",
                "test_discovery_ideas.py::test_owner_scope_revocation_session_origin_and_csrf",
            ),
        ),
        (
            "POST",
            "/digest",
            credited(
                "asserts a holder of the same private scope gets 404 on preview and 409 on download, a revoked "
                "grant 403, no session 401; the other-scope and changed-record cases refuse the whole copy",
                "test_discovery_digest.py::test_owner_scope_session_origin_csrf_and_session_bound_review",
                "test_discovery_digest.py::test_feedback_change_forgetting_and_other_scope_record_refuse_whole_copy",
            ),
        ),
    ],
)
group(
    "/api/v1/document-answers",
    [
        (
            "POST",
            "",
            credited(
                "answers and citations exclude foreign private sources alone and mixed, on a live revoked grant "
                "and a replayed logged-out session, on SQLite and the restricted PostgreSQL role",
                *docs_tests(
                    "test_answers_exclude_foreign_private_sources_alone_and_mixed",
                    "test_grant_revocation_withholds_documents_and_answers_on_a_live_session",
                    "test_replaying_a_logged_out_session_credential_releases_nothing",
                ),
            ),
        ),
    ],
)
group(
    "/api/v1/documents",
    [
        ("POST", "", swept("documents", "create")),
        ("POST", "/query", swept("documents", "listing")),
        ("POST", "/export", swept("documents", "export")),
        ("POST", "/{identifier}/read", swept("documents", "read")),
        ("POST", "/{identifier}/history", swept("documents", "history")),
        ("POST", "/{identifier}/original", swept("documents", "by_id:original")),
        ("POST", "/{identifier}/excerpt", swept("documents", "by_id:excerpt")),
        ("POST", "/{identifier}/correct", swept("documents", "mutation:correct")),
        ("POST", "/{identifier}/replace", swept("documents", "mutation:replace")),
        ("POST", "/{identifier}/forget", swept("documents", "mutation:forget")),
        (
            "POST",
            "/{identifier}/archive",
            excluded(
                "uncovered limitation: needs a configured durable archive root; existing archive tests "
                "(test_document_archiving.py) are lifecycle tests, none with a foreign actor"
            ),
        ),
        (
            "POST",
            "/{identifier}/archive/status",
            excluded(
                "uncovered limitation: needs a configured durable archive root; no foreign-actor test"
            ),
        ),
        (
            "POST",
            "/{identifier}/extract",
            excluded(
                "uncovered limitation: needs the PDF worker contract; existing PDF tests "
                "(test_pdf_ingestion.py) cover the owner-bound upload key, none a foreign actor"
            ),
        ),
    ],
)
group(
    "/api/v1/email-intake",
    [
        ("POST", "", swept("email-intake", "create")),
        ("POST", "/{identifier}/read", swept("email-intake", "read")),
        ("POST", "/{identifier}/export", swept("email-intake", "export_one")),
    ],
)
group(
    "/api/v1/filing",
    [
        (
            "POST",
            "/request",
            excluded(
                "uncovered limitation: a filing exists only after a reviewed invoice, an approved plan and the "
                "worker pipeline, which this harness has no fixtures for; "
                "test_filing.py::test_only_the_owner_can_request_and_others_cannot_see_filings checks another "
                "user's request only as a status set {403, 404}"
            ),
        ),
        (
            "POST",
            "/cancel",
            excluded(
                "uncovered limitation: needs a seeded filing; "
                "test_filing.py::test_owner_can_cancel_only_work_that_has_not_started is owner-only"
            ),
        ),
        (
            "POST",
            "/query",
            excluded(
                "uncovered limitation: needs a seeded filing; the existing test checks another user's page as "
                "{200, 403} without the id present"
            ),
        ),
        (
            "POST",
            "/history",
            excluded(
                "uncovered limitation: needs a seeded filing; the existing test accepts {403, 404}"
            ),
        ),
    ],
)
group(
    "/api/v1/finance",
    [
        ("POST", "", swept("finance", "create")),
        ("POST", "/query", swept("finance", "listing")),
        ("POST", "/export", swept("finance", "export")),
        ("POST", "/{identifier}/read", swept("finance", "read")),
        ("POST", "/{identifier}/history", swept("finance", "history")),
        ("POST", "/{identifier}/export", swept("finance", "export_one")),
        ("POST", "/{identifier}/correct", swept("finance", "mutation:correct")),
        ("POST", "/{identifier}/accept", swept("finance", "mutation:accept")),
        ("POST", "/{identifier}/forget", swept("finance", "mutation:forget")),
    ],
)
add("GET", "/api/v1/health", excluded("unauthenticated liveness: no stored data, no identifier"))
add("GET", "/api/v1/live", excluded("unauthenticated liveness: no stored data, no identifier"))
add(
    "GET",
    "/api/v1/system/summary",
    excluded("returns no body; only requires the identity foundation"),
)
group(
    "/api/v1/installation",
    [
        (m, "/" + t, swept("installation", "admin"))
        for m, t in (
            ("POST", "apply"),
            ("POST", "export"),
            ("POST", "history"),
            ("POST", "preview"),
            ("POST", "read"),
        )
    ],
)
group(
    "/api/v1/invoices",
    [
        ("POST", "/{identifier}/read", swept("invoices", "read")),
        ("POST", "/{identifier}/history", swept("invoices", "history")),
        ("POST", "/{identifier}/duplicates", swept("invoices", "by_id:duplicates")),
        ("POST", "/{identifier}/export", swept("invoices", "export_one")),
        ("POST", "/{identifier}/prepare", swept("invoices", "mutation:prepare")),
        ("POST", "/{identifier}/review", swept("invoices", "mutation:review")),
        ("POST", "/{identifier}/forget", swept("invoices", "mutation:forget")),
        *[
            (
                "POST",
                f"/{{identifier}}/{op}",
                credited(
                    "asserts a holder of the same private scope gets 404 for plan, approve_plan and withdraw_plan "
                    "and that a revoked grant is refused with 403",
                    "test_invoice_filing.py::test_plan_private_admin_revocation_and_request_boundaries",
                ),
            )
            for op in ("plan", "approve_plan", "withdraw_plan")
        ],
    ],
)
group(
    "/api/v1/jobs",
    [
        (
            "POST",
            "",
            excluded(
                "uncovered limitation: job creation needs the queued-job fixture and technical-job authority; no "
                "foreign-actor create test exists"
            ),
        ),
        (
            "GET",
            "/{identifier}",
            credited(
                "asserts another user gets 404 for the job id and for a random id",
                "test_jobs.py::test_scope_privacy_and_review_csrf",
            ),
        ),
        (
            "POST",
            "/{identifier}/review",
            credited(
                "asserts a 403 for the requester's own review; weaker than this suite (one actor)",
                "test_jobs.py::test_scope_privacy_and_review_csrf",
            ),
        ),
    ],
)
group(
    "/api/v1/memory",
    [
        ("POST", "", swept("memory", "create")),
        ("GET", "", swept("memory", "listing")),
        ("GET", "/export", swept("memory", "export")),
        ("GET", "/{identifier}", swept("memory", "read")),
        ("GET", "/{identifier}/history", swept("memory", "history")),
        ("PATCH", "/{identifier}", swept("memory", "mutation:correct")),
        ("POST", "/{identifier}/forget", swept("memory", "mutation:forget")),
    ],
)
group(
    "/api/v1/notifications",
    [
        (
            "POST",
            "/query",
            excluded(
                "uncovered limitation: a notification exists only after a delivered reminder and the notification "
                "worker with a synthetic channel, which this harness has no fixtures for; "
                "test_notifications.py::test_bounded_pass_and_cross_user_isolation asserts only a status set for "
                "the owner's other scope and for no session, with no foreign notification seeded"
            ),
        ),
        (
            "POST",
            "/history",
            excluded(
                "uncovered limitation: needs a seeded notification; the existing test asserts only a 404 for a "
                "random delivery id"
            ),
        ),
    ],
)
group(
    "/api/v1/operations",
    [
        ("POST", "/read", swept("operations", "admin")),
        ("POST", "/audit-summary", swept("operations", "admin")),
        ("POST", "/work-status", swept("operations", "admin")),
    ],
)
group(
    "/api/v1/reminders",
    [
        ("POST", "/action", swept("reminders", "mutation:cancel")),
        ("POST", "/export", swept("reminders", "export")),
        ("POST", "/history", swept("reminders", "history")),
        ("POST", "/query", swept("reminders", "listing")),
        ("POST", "/read", swept("reminders", "read")),
        ("POST", "/schedule", swept("reminders", "mutation:schedule")),
        ("POST", "/preferences/read", swept("reminders", "preferences")),
        ("POST", "/preferences/save", swept("reminders", "preferences")),
    ],
)
group(
    "/api/v1/routines",
    [
        ("POST", "", swept("routines", "create")),
        ("POST", "/query", swept("routines", "listing")),
        ("POST", "/{identifier}/read", swept("routines", "read")),
        ("POST", "/{identifier}/history", swept("routines", "history")),
        ("POST", "/{identifier}/export", swept("routines", "export_one")),
        ("POST", "/{identifier}/occurrences", swept("routines", "by_id:occurrences")),
        ("POST", "/{identifier}/correct", swept("routines", "mutation:correct")),
        ("POST", "/{identifier}/action", swept("routines", "mutation:pause")),
        (
            "POST",
            "/preview",
            excluded(
                "stateless: computes a plan from the caller's own submitted values; reads no stored record"
            ),
        ),
    ],
)
group(
    "/api/v1/speech",
    [
        (
            "GET",
            "/status",
            excluded(
                "speech is disabled by default and holds no stored record; reports a configuration flag"
            ),
        ),
        (
            "POST",
            "/synthesize",
            excluded(
                "stateless text-to-speech of the caller's own submitted text; no stored record"
            ),
        ),
    ],
)
group(
    "/api/v1/tasks",
    [
        ("POST", "", swept("tasks", "create")),
        ("POST", "/query", swept("tasks", "listing")),
        ("POST", "/export", swept("tasks", "export")),
        ("POST", "/{identifier}/read", swept("tasks", "read")),
        ("POST", "/{identifier}/history", swept("tasks", "history")),
        ("POST", "/{identifier}/correct", swept("tasks", "mutation:correct")),
        ("POST", "/{identifier}/transition", swept("tasks", "mutation:transition")),
        ("POST", "/{identifier}/forget", swept("tasks", "mutation:forget")),
    ],
)


def classified(operations):
    """The static entries plus every registered Work operation, excluded with the boundary statement.
    Returns a new dictionary each call."""
    entries = dict(ENTRIES)
    for method, path in operations:
        if path.startswith("/api/v1/work"):
            assert (method, path) not in entries, (method, path)
            entries[(method, path)] = excluded(WORK_REASON)
    return entries


NOT_PAGINATED = {
    "view": "a single bounded snapshot (a briefing); it has no cursor",
    "by_id": "a by-ID operation: its pages, where it has any, are the record's own revisions, "
    "so no other holder's record can occupy a position in the sequence",
    "history": "paged per record by revision; the sequence belongs to one record, so no other "
    "holder's record can occupy a position in it",
    "export_one": "an export of one record's revisions, paged per record by revision",
}
NOT_COVERED_BOUNDARY = {
    "discovery": "uncovered limitation: the listing orders by a computed score and then the id, "
    "so a key can be placed relative to a boundary only through the score; multi-page walks, foreign "
    "cursor replay and exact visible sets are swept, positions around the boundary are not placed",
}


def pagination(entries):
    """For every swept listing, export or view route, how its pagination is covered:
    ``boundary`` (page-boundary cases with foreign keys beside every boundary), ``not applicable``
    (with the reason) or ``uncovered limitation``. Routes without pagination in this suite's sense
    are not listed."""
    out = {}
    for key, entry in entries.items():
        if entry.kind != "swept":
            continue
        kind, _, _ = entry.what.partition(":")
        if kind in {"listing", "export"}:
            out[key] = (
                ("uncovered limitation", NOT_COVERED_BOUNDARY[entry.adapter])
                if entry.adapter in NOT_COVERED_BOUNDARY
                else ("boundary", entry.adapter)
            )
        elif kind == "view":
            out[key] = (
                ("uncovered limitation", NOT_COVERED_BOUNDARY[entry.adapter])
                if entry.adapter in NOT_COVERED_BOUNDARY
                else ("not applicable", NOT_PAGINATED["view"])
            )
        elif kind in {"history", "export_one"}:
            out[key] = ("not applicable", NOT_PAGINATED["history"])
    return out
