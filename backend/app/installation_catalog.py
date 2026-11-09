"""Informational build/setup catalogue, never a feature permission or activation switch."""

from app.config import settings

CAPABILITIES = (
    (
        "core.identity_audit",
        (),
        True,
        None,
        "Available in this development build; current grants remain mandatory.",
    ),
    (
        "core.installation",
        ("core.identity_audit",),
        True,
        "installation",
        "Versioned defaults and identity only; member onboarding and feature controls remain open.",
    ),
    (
        "documents.library",
        ("core.identity_audit",),
        False,
        None,
        "Bounded originals/review; archive and parser setup are separate.",
    ),
    (
        "documents.pdf_ocr",
        ("documents.library",),
        False,
        "parser",
        "Requires the separately configured isolated parser; this view does not probe it.",
    ),
    (
        "documents.archive",
        ("documents.library",),
        False,
        "archive",
        "Configured path is not proof of availability, integrity or recovery.",
    ),
    (
        "documents.answers",
        ("documents.library",),
        False,
        "answers",
        "Environment-controlled local selector; no model is selected or activated here.",
    ),
    (
        "documents.invoices",
        ("documents.library",),
        False,
        None,
        "Reviewed fields/plans; plan approval grants no filing authority.",
    ),
    (
        "intake.offline_email",
        ("documents.library",),
        False,
        None,
        "Bounded offline originals, not a connected mailbox.",
    ),
    (
        "tasks.manual",
        ("core.identity_audit",),
        False,
        None,
        "Manual task records remain deterministic and scoped.",
    ),
    (
        "routines.finite",
        ("tasks.manual",),
        False,
        None,
        "Finite controls available; generation needs the separately started worker.",
    ),
    (
        "notifications.in_app",
        ("tasks.manual",),
        False,
        None,
        "In-app policy/records; consumer status and external delivery are not verified here.",
    ),
    (
        "calendar.manual",
        ("core.identity_audit",),
        False,
        None,
        "Normalized manual/synthetic windows, not a live calendar account.",
    ),
    (
        "work.synthetic",
        ("core.identity_audit",),
        False,
        "work",
        "Synthetic pilot only; real professional sources need separate acceptance.",
    ),
    (
        "providers.live",
        ("core.identity_audit",),
        False,
        "planned",
        "Live sources/effects require separately authorized adapters and acceptance.",
    ),
)


def validate_graph(items):
    graph = {item[0]: item[1] for item in items}
    if len(graph) != len(items) or any(dep not in graph for deps in graph.values() for dep in deps):
        raise ValueError("Unknown or duplicate capability key")
    done, visiting = set(), set()

    def visit(key):
        if key in visiting:
            raise ValueError("Cyclic capability graph")
        if key in done:
            return
        visiting.add(key)
        for dep in graph[key]:
            visit(dep)
        visiting.remove(key)
        done.add(key)

    for key in graph:
        visit(key)


validate_graph(CAPABILITIES)


def catalogue(configured):
    flags = {
        "parser": settings.pdf_socket_directory is not None,
        "archive": settings.document_archive_directory is not None,
        "answers": settings.document_answers_enabled,
        "work": settings.work_synthetic_adapter_enabled,
    }
    result = []
    for key, deps, mandatory, kind, notice in CAPABILITIES:
        status = (
            "available_in_development"
            if kind is None
            else "configured"
            if kind == "installation" and configured
            else "setup_required"
            if kind == "installation"
            else "separate_authorization_required"
            if kind == "planned"
            else "configured_unverified"
            if flags[kind]
            else "disabled_by_environment"
            if kind in {"answers", "work"}
            else "operator_setup_required"
        )
        result.append(
            {
                "key": key,
                "dependencies": list(deps),
                "mandatory": mandatory,
                "readiness": status,
                "activation_control": "not_provided",
                "live_verified": False,
                "notice": notice,
            }
        )
    return result
