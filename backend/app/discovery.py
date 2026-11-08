"""Manual owner-private proposals. Feedback is interest, never action authority."""

from datetime import timedelta
from ipaddress import ip_address
from typing import Literal
from urllib.parse import urlsplit

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, ValidationError, field_validator
from sqlalchemy import String, case, cast, func, or_, select

from app import approvals, identity, memory
from app.models import MemoryRecord

SCOPES = frozenset({"member_a_private", "member_b_private"})
Choice = Literal["very_interested", "later", "covered", "not_relevant"]
SCORES = {"very_interested": 100, "later": 10, "covered": -10, "not_relevant": -20}


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class Evidence(Strict):
    title: str = Field(min_length=1, max_length=160)
    url: str = Field(min_length=1, max_length=512)
    observed_at: AwareDatetime

    @field_validator("url")
    @classmethod
    def inert_public_reference(cls, value):
        # No DNS resolution or fetching. This is not an egress/SSRF allowlist.
        parts = urlsplit(value)
        host = parts.hostname or ""
        if (
            parts.scheme != "https"
            or not host
            or "." not in host
            or parts.username is not None
            or parts.password is not None
            or parts.port not in {None, 443}
            or host.endswith((".localhost", ".local", ".internal"))
            or any(ord(c) < 33 for c in value)
        ):
            raise ValueError("An inert public HTTPS reference is required")
        try:
            address = ip_address(host)
        except ValueError:
            pass
        else:
            if not address.is_global:
                raise ValueError("Private references are unavailable")
        return value

    @field_validator("observed_at")
    @classmethod
    def not_future(cls, value):
        if value > identity.now_utc() + timedelta(minutes=5):
            raise ValueError("Evidence date cannot be in the future")
        return value


class Proposal(Strict):
    topic: str = Field(pattern=r"^[a-z0-9][a-z0-9-]{0,63}$")
    summary: str = Field(min_length=1, max_length=1000)
    evidence: list[Evidence] = Field(min_length=1, max_length=5)
    benefit: str = Field(min_length=1, max_length=512, default="Not assessed")
    privacy: str = Field(min_length=1, max_length=512, default="Not assessed")
    maturity_license: str = Field(min_length=1, max_length=512, default="Not assessed")
    hardware_cost: str = Field(min_length=1, max_length=512, default="Not assessed")
    alternatives_dependencies: str = Field(min_length=1, max_length=512, default="Not assessed")
    experiment: str = Field(min_length=1, max_length=1000, default="Not proposed")


class Feedback(Strict):
    choice: Choice | None
    note: str = Field(max_length=500, default="")
    recorded_at: AwareDatetime


class Envelope(Proposal):
    record_type: Literal["discovery_proposal"]
    schema_version: Literal[1]
    feedback: Feedback | None = None


class IdeaEnvelope(Envelope):
    schema_version: Literal[2]
    stage: Literal["idea"] = "idea"
    topic: str = Field(default="unclassified", pattern=r"^[a-z0-9][a-z0-9-]{0,63}$")
    evidence: list[Evidence] = Field(default_factory=list, max_length=0)


class ProposalEnvelope(Envelope):
    schema_version: Literal[2]
    stage: Literal["proposal"] = "proposal"


def parse(record):
    if record.kind != "experience" or record.state != "active" or memory.expired(record):
        return None
    try:
        content = record.content
        if not isinstance(content, dict):
            return None
        if content.get("schema_version") == 2 and content.get("stage") not in {"idea", "proposal"}:
            return None
        if content.get("schema_version") == 2:
            model = IdeaEnvelope if content.get("stage") == "idea" else ProposalEnvelope
        else:
            model = Envelope
        return model.model_validate(content)
    except (ValidationError, TypeError, ValueError):
        return None


def document(record, envelope):
    return dict(
        memory.document(record),
        priority=SCORES.get(envelope.feedback.choice, 0) if envelope.feedback else 0,
        action_authority="interest_only",
    )


def create(db, token, csrf, scope, title, proposal, *, idea=False):
    if scope not in SCOPES:
        # Keep the normal authenticated/CSRF decision before scope rejection.
        actor = approvals.actor(db, token, csrf, True)
        if isinstance(actor, identity.Result):
            return actor
        return identity.denied(db, 403, "discovery.scope_denied", user=actor[0])
    values = {
        "title": title,
        "content": (
            IdeaEnvelope(record_type="discovery_proposal", schema_version=2, **proposal)
            if idea
            else Envelope(
                record_type="discovery_proposal", schema_version=1, **proposal.model_dump()
            )
        ).model_dump(mode="json"),
        "source_type": "manual",
        "source_reference": (
            "Manually entered Discovery idea; no evidence supplied"
            if idea
            else "Manually entered Discovery proposal; evidence not verified"
        ),
        "assessment": "tentative",
        "expires_at": None,
    }
    result = memory.create(db, token, csrf, scope, "experience", values)
    if result.status == 201:
        result.payload.update(priority=0, action_authority="interest_only")
    return result


def operate(
    db, token, csrf, identifier, expected=None, choice=None, note="", *, details=None, title=None
):
    unsafe = expected is not None
    actor = approvals.actor(db, token, csrf, unsafe)
    if isinstance(actor, identity.Result):
        return actor
    user, session, scopes = actor
    query = select(MemoryRecord).where(
        MemoryRecord.id == identifier,
        MemoryRecord.owner_id == user.id,
        MemoryRecord.scope_key.in_(SCOPES & set(scopes)),
    )
    record = db.scalar(query.with_for_update() if unsafe else query)
    envelope = parse(record) if record else None
    if envelope is None:
        return identity.denied(db, 404, "discovery.not_found", user=user)
    if unsafe:
        if record.revision != expected:
            return identity.denied(db, 409, "discovery.revision_conflict", user=user)
        was_idea = isinstance(envelope, IdeaEnvelope)
        if details is not None:
            envelope = ProposalEnvelope(
                record_type="discovery_proposal",
                schema_version=2,
                feedback=envelope.feedback,
                **details.model_dump(),
            )
        else:
            envelope.feedback = (
                Feedback(choice=choice, note=note, recorded_at=identity.now_utc())
                if choice is not None or note
                else None
            )
        values = {
            "title": title if details is not None else record.title,
            "content": envelope.model_dump(mode="json"),
            "source_type": record.source_type,
            "source_reference": (
                "Manually entered Discovery proposal; evidence not verified"
                if details is not None
                and was_idea
                and record.source_reference
                == "Manually entered Discovery idea; no evidence supplied"
                else record.source_reference
            ),
            "assessment": record.assessment,
            "expires_at": record.expires_at,
        }
        result = memory.operate(
            db, token, csrf, identifier, operation="correct", expected=expected, values=values
        )
        if result.status != 200:
            return result
    else:
        memory.audit(db, user, record, "read")
    session.last_seen_at = identity.now_utc()
    identity.audit(
        db,
        ("discovery.details" if details is not None else "discovery.feedback")
        if unsafe
        else "discovery.read",
        "success",
        user=user,
        scope=record.scope_key,
        entity=str(record.id),
        entity_type="memory",
        after={"revision": record.revision},
    )
    return identity.Result(200, document(record, envelope))


class InboxFilters(Strict):
    q: str = Field(default="", max_length=120)
    topic: str | None = Field(default=None, pattern=r"^[a-z0-9][a-z0-9-]{0,63}$")
    stage: Literal["all", "idea", "proposal"] = "all"
    interest: Literal[
        "all", "unanswered", "very_interested", "later", "covered", "not_relevant"
    ] = "all"

    @field_validator("q", mode="before")
    @classmethod
    def single_line(cls, value):
        if not isinstance(value, str) or any(ord(c) < 32 or ord(c) == 127 for c in value):
            raise ValueError("A single-line search is required")
        return value


def listing(
    db,
    token,
    limit,
    after,
    after_priority,
    include_dismissed,
    filters=None,
    *,
    csrf=None,
    locked=False,
):
    actor = approvals.actor(db, token, csrf, locked)
    if isinstance(actor, identity.Result):
        return actor
    user, session, scopes = actor
    if (after is None) != (after_priority is None) or (
        after_priority is not None and after_priority not in {0, *SCORES.values()}
    ):
        return identity.denied(db, 422, "discovery.invalid_cursor", user=user)
    choice = MemoryRecord.content["feedback"]["choice"].as_string()
    score = case(*[(choice == key, value) for key, value in SCORES.items()], else_=0)
    query = select(MemoryRecord).where(
        MemoryRecord.owner_id == user.id,
        MemoryRecord.scope_key.in_(SCOPES & set(scopes)),
        MemoryRecord.state == "active",
        MemoryRecord.kind == "experience",
        or_(MemoryRecord.expires_at.is_(None), MemoryRecord.expires_at > identity.now_utc()),
        MemoryRecord.content["record_type"].as_string() == "discovery_proposal",
    )
    filters = filters or InboxFilters()
    if filters.q:
        text = filters.q.lower()
        query = query.where(
            or_(
                func.lower(MemoryRecord.title).contains(text, autoescape=True),
                func.lower(MemoryRecord.content["summary"].as_string()).contains(
                    text, autoescape=True
                ),
            )
        )
    if filters.topic is not None:
        query = query.where(MemoryRecord.content["topic"].as_string() == filters.topic)
    if filters.stage == "idea":
        query = query.where(
            cast(MemoryRecord.content["schema_version"].as_string(), String) == "2",
            MemoryRecord.content["stage"].as_string() == "idea",
        )
    elif filters.stage == "proposal":
        query = query.where(
            or_(
                cast(MemoryRecord.content["schema_version"].as_string(), String) == "1",
                (cast(MemoryRecord.content["schema_version"].as_string(), String) == "2")
                & (MemoryRecord.content["stage"].as_string() == "proposal"),
            )
        )
    if filters.interest != "all":
        query = query.where(
            choice.is_(None) if filters.interest == "unanswered" else choice == filters.interest
        )
    if not include_dismissed:
        query = query.where(score >= 0)
    if after is not None:
        query = query.where(
            or_(score < after_priority, (score == after_priority) & (MemoryRecord.id > after))
        )
    rows = db.scalars(query.order_by(score.desc(), MemoryRecord.id).limit(limit + 1)).all()
    envelopes = [parse(row) for row in rows]
    if any(envelope is None for envelope in envelopes):
        return identity.denied(db, 422, "discovery.invalid_record", user=user)
    items = [document(row, envelope) for row, envelope in zip(rows[:limit], envelopes[:limit])]
    session.last_seen_at = identity.now_utc()
    identity.audit(db, "discovery.list", "success", user=user, metadata={"returned": len(items)})
    cursor = (
        {"id": items[-1]["id"], "priority": items[-1]["priority"]} if len(rows) > limit else None
    )
    return identity.Result(200, {"schema_version": 1, "items": items, "next_cursor": cursor})
