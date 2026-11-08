"""Ephemeral scoped exact-source answers. Source text grants no execution authority."""

import json
import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Literal
from uuid import UUID, uuid4

from pydantic import Field, field_validator
from sqlalchemy import case, func, or_, select

from app import answer_adapter, documents, identity
from app.manual_tasks import Scoped, authority, stamp
from app.models import DocumentRecord

STOP = frozenset(
    [
        "what",
        "is",
        "the",
        "a",
        "an",
        "of",
        "in",
        "for",
        "to",
        "and",
        "how",
        "which",
        "please",
        "show",
        "tell",
        "me",
        "que",
        "qué",
        "cuál",
        "cual",
        "es",
        "el",
        "la",
        "los",
        "las",
        "un",
        "una",
        "de",
        "en",
        "por",
        "para",
        "y",
        "le",
        "les",
        "des",
        "du",
        "quelle",
        "quel",
        "est",
        "sont",
        "une",
        "et",
        "dans",
        "sur",
        "pour",
        "comment",
        "montant",
    ]
)


class Question(Scoped):
    question: str = Field(min_length=2, max_length=500)
    language: Literal["en", "fr", "es"] = "en"
    max_bytes: int = Field(strict=True, ge=1024, le=8192, default=8192)

    @field_validator("question")
    @classmethod
    def safe_question(cls, value):
        if not value.strip() or any(ord(c) < 32 or 0xD800 <= ord(c) <= 0xDFFF for c in value):
            raise ValueError("Invalid question")
        return value.strip()


@dataclass
class Plan:
    actor_id: UUID
    request_id: str
    sources: list
    valid_until: datetime
    configuration: tuple


def encoded(value):
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    ).encode()


def evidence(row, source, start, end, user):
    lines = row.content_text.split("\n")
    spans = (
        []
        if row.extraction_json is None
        else [
            dict(
                span, start_line=max(start, span["start_line"]), end_line=min(end, span["end_line"])
            )
            for span in row.extraction_json["page_spans"]
            if span["start_line"] <= end and span["end_line"] >= start
        ]
    )
    return {
        "source": source,
        "document": documents.presented(row, user, text=False),
        "start_line": start,
        "end_line": end,
        "text": "\n".join(lines[start - 1 : end]),
        "page_spans": spans,
    }


def audit(db, user, scope, request_id, event, sources, **extra):
    identity.audit(
        db,
        "answers." + event,
        "success",
        user=user,
        scope=scope,
        entity_type="document_answer",
        entity=request_id,
        metadata={
            "sources": [
                {
                    "id": item["document"]["id"],
                    "revision": item["document"]["revision"],
                    "start_line": item["start_line"],
                    "end_line": item["end_line"],
                }
                for item in sources
            ],
            **extra,
        },
    )


def response(body, request_id, sources, expiry, status, *, invoked=False, passages=None):
    return {
        "schema_version": 1,
        "request_id": request_id,
        "scope": body.scope,
        "language": body.language,
        "status": status,
        "model_invoked": invoked,
        "execution_allowed": False,
        "generated_at": stamp(identity.now_utc()),
        "valid_until": stamp(expiry),
        "max_bytes": body.max_bytes,
        "sources": sources,
        "passages": passages or [],
        "notice": "Bounded lexical source selection; relevance and source truth are not independently verified. OCR recognition remains uncertain. No tool or external action is authorized.",
    }


def prepare(db, token, csrf, body):
    current = authority(db, token, csrf, body.scope, event_prefix="answers")
    if isinstance(current, identity.Result):
        return current, None
    user, session = current
    now = identity.now_utc()
    if not identity.attempt(db, "document-answers:" + str(user.id), 30, now):
        return identity.denied(db, 429, "answers.rate_limited", user=user), None
    terms = list(
        dict.fromkeys(
            term for term in re.findall(r"[^\W_]+", body.question.lower()) if term not in STOP
        )
    )[:8]
    sources = []
    if terms:
        matches = [
            func.lower(DocumentRecord.content_text).contains(term, autoescape=True)
            for term in terms
        ]
        score = sum(case((match, 1), else_=0) for match in matches)
        rows = db.scalars(
            select(DocumentRecord)
            .where(
                *documents.visible(user, body.scope),
                DocumentRecord.state == "active",
                DocumentRecord.reviewed.is_(True),
                or_(*matches),
            )
            .order_by(score.desc(), DocumentRecord.id)
            .limit(3)
            .with_for_update(read=True)
        ).all()
        for row in rows:
            lines = row.content_text.split("\n")
            line = next(
                (i for i, text in enumerate(lines) if any(term in text.lower() for term in terms)),
                None,
            )
            if line is not None:
                sources.append(
                    evidence(row, len(sources) + 1, line + 1, min(len(lines), line + 8), user)
                )
    if len(encoded(sources)) > body.max_bytes:
        return identity.denied(db, 413, "answers.context_limit", user=user, scope=body.scope), None
    if identity.resolve(db, token, refresh_session=True) is None:
        return identity.denied(db, 401, "answers.session_denied", user=user), None
    expiry = min(now + timedelta(seconds=60), identity.aware(session.expires_at))
    identifier = str(uuid4())
    configured = answer_adapter.configuration()
    enabled = configured[0]
    status = "no_sources" if not sources else "prepared" if enabled else "source_only"
    audit(
        db,
        user,
        body.scope,
        identifier,
        "prepared" if status == "prepared" else status,
        sources,
        items_bytes=len(encoded(sources)),
        adapter="local-passages-v1" if status == "prepared" else None,
        model=configured[2] if status == "prepared" else None,
        digest=configured[3] if status == "prepared" else None,
    )
    plan = Plan(user.id, identifier, sources, expiry, configured) if status == "prepared" else None
    return identity.Result(200, response(body, identifier, sources, expiry, status)), plan


def validate_selection(value, sources):
    if (
        not isinstance(value, dict)
        or set(value) != {"status", "passages"}
        or value["status"] not in {"answer", "insufficient", "conflicting"}
        or not isinstance(value["passages"], list)
        or len(value["passages"]) > 5
    ):
        raise ValueError("Invalid selection")
    if value["status"] != "answer":
        if value["passages"]:
            raise ValueError("Invalid abstention")
        return value["status"], []
    if not value["passages"]:
        raise ValueError("Missing citations")
    passages = []
    ranges = []
    for selected in value["passages"]:
        if (
            not isinstance(selected, dict)
            or set(selected) != {"source", "start_line", "end_line"}
            or any(type(v) is not int for v in selected.values())
        ):
            raise ValueError("Invalid citation")
        source, start, end = (selected[key] for key in ("source", "start_line", "end_line"))
        if not 1 <= source <= len(sources):
            raise ValueError("Unknown citation")
        original = sources[source - 1]
        if not original["start_line"] <= start <= end <= original["end_line"] or any(
            slot == source and a <= end and b >= start for slot, a, b in ranges
        ):
            raise ValueError("Invalid citation range")
        ranges.append((source, start, end))
        item = dict(
            original,
            start_line=start,
            end_line=end,
            text="\n".join(
                original["text"].split("\n")[
                    start - original["start_line"] : end - original["start_line"] + 1
                ]
            ),
            page_spans=[
                dict(
                    span,
                    start_line=max(start, span["start_line"]),
                    end_line=min(end, span["end_line"]),
                )
                for span in original["page_spans"]
                if span["start_line"] <= end and span["end_line"] >= start
            ],
        )
        passages.append(item)
    if len(encoded(passages)) > 8192:
        raise ValueError("Answer limit")
    return "answered", passages


def dispatch(db, token, csrf, body, plan):
    current = authority(db, token, csrf, body.scope, event_prefix="answers")
    if isinstance(current, identity.Result):
        return current
    user, session = current
    if (
        user.id != plan.actor_id
        or plan.configuration != answer_adapter.configuration()
        or identity.now_utc() >= plan.valid_until
    ):
        return identity.denied(db, 409, "answers.preparation_changed", user=user)
    identifiers = [UUID(item["document"]["id"]) for item in plan.sources]
    rows = db.scalars(
        select(DocumentRecord)
        .where(
            DocumentRecord.id.in_(identifiers),
            *documents.visible(user, body.scope),
            DocumentRecord.state == "active",
            DocumentRecord.reviewed.is_(True),
        )
        .order_by(DocumentRecord.id)
        .with_for_update(read=True)
        .execution_options(populate_existing=True)
    ).all()
    records = {str(row.id): row for row in rows}
    sources = []
    for old in plan.sources:
        row = records.get(old["document"]["id"])
        if row is None or row.revision != old["document"]["revision"]:
            return identity.denied(db, 409, "answers.sources_changed", user=user)
        rebuilt = evidence(row, old["source"], old["start_line"], old["end_line"], user)
        if rebuilt != old:
            return identity.denied(db, 409, "answers.sources_changed", user=user)
        sources.append(rebuilt)
    if identity.resolve(db, token, refresh_session=True) is None:
        return identity.denied(db, 401, "answers.session_denied", user=user)
    outcome = answer_adapter.select_passages(body.question, body.language, sources)
    status, passages = "unavailable", []
    if outcome["status"] == "selected":
        try:
            status, passages = validate_selection(outcome["selection"], sources)
        except (ValueError, TypeError):
            status = "invalid_answer"
    if identity.resolve(db, token, refresh_session=True) is None:
        return identity.denied(db, 401, "answers.session_denied", user=user)
    if identity.now_utc() >= plan.valid_until:
        return identity.denied(db, 409, "answers.preparation_expired", user=user)
    audit(
        db,
        user,
        body.scope,
        plan.request_id,
        status,
        sources,
        model_invoked=outcome["invoked"],
        model=plan.configuration[2],
        digest=plan.configuration[3],
        passages=[
            {key: item[key] for key in ("source", "start_line", "end_line")} for item in passages
        ],
    )
    return identity.Result(
        200,
        response(
            body,
            plan.request_id,
            sources,
            min(plan.valid_until, identity.aware(session.expires_at)),
            status,
            invoked=outcome["invoked"],
            passages=passages,
        ),
    )
