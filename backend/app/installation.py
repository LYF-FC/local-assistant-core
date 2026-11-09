"""Current-admin installation defaults/templates; no onboarding, activation or secret effects."""

import hashlib
import hmac
import json
import re
from datetime import timedelta
from typing import Literal
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import select

from app import identity, installation_catalog
from app.manual_tasks import authority, stamp
from app.models import InstallationConfig, InstallationRevision


class Schema(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)


class Defaults(Schema):
    languages: list[Literal["en", "fr", "es"]] = Field(min_length=1, max_length=3)
    timezone: str = Field(min_length=1, max_length=64)

    @field_validator("languages")
    @classmethod
    def unique_languages(cls, value):
        if len(set(value)) != len(value):
            raise ValueError("Duplicate language")
        return value

    @field_validator("timezone")
    @classmethod
    def valid_zone(cls, value):
        if not re.fullmatch(r"[A-Za-z0-9_+./-]+", value):
            raise ValueError("IANA timezone required")
        try:
            ZoneInfo(value)
        except (ValueError, ZoneInfoNotFoundError):
            raise ValueError("IANA timezone required") from None
        return value


class Template(Schema):
    schema_version: Literal[1]
    defaults: Defaults

    @field_validator("schema_version", mode="before")
    @classmethod
    def explicit_version(cls, value):
        if type(value) is not int or value != 1:
            raise ValueError("Supported schema required")
        return value


class Admin(Schema):
    scope: Literal["technical_admin"]


class Expected(Admin):
    expected_revision: int = Field(strict=True, ge=0, le=100)
    expected_installation_id: UUID | None


class Preview(Expected):
    template: Template


class Apply(Preview):
    preview_token: str = Field(pattern=r"^[a-f0-9]{64}$")
    expires_at: AwareDatetime
    confirm: Literal[True]

    @field_validator("confirm", mode="before")
    @classmethod
    def explicit(cls, value):
        if value is not True:
            raise ValueError("Explicit confirmation required")
        return value


class Export(Expected):
    acknowledge_copy_limits: Literal[True]
    _explicit = field_validator("acknowledge_copy_limits", mode="before")(Apply.explicit.__func__)


class History(Admin):
    after: int = Field(default=0, strict=True, ge=0, le=100)


def saved(row):
    return {
        "installation_id": str(row.installation_id) if row.installation_id else None,
        "revision": row.revision,
        "configuration": row.configuration,
        "updated_by": str(row.updated_by) if row.updated_by else None,
        "created_at": stamp(row.created_at),
        "updated_at": stamp(row.updated_at),
    }


def view(row):
    return {
        "schema_version": 1,
        "record": saved(row),
        "catalogue": installation_catalog.catalogue(row.revision > 0),
        "notice": "Development setup defaults only. Existing member scopes and runtime controls remain unchanged; readiness is not health, permission or feature activation.",
    }


def audit(db, user, row, operation, **metadata):
    identity.audit(
        db,
        "installation." + operation,
        "success",
        user=user,
        scope="technical_admin",
        entity_type="installation",
        entity=str(row.installation_id) if row.installation_id else "unconfigured",
        metadata={"revision": row.revision, **metadata},
    )


def token(session, row, template, expires):
    payload = json.dumps(
        {
            "installation_id": str(row.installation_id) if row.installation_id else None,
            "revision": row.revision,
            "template": template,
            "expires_at": stamp(expires),
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return hmac.new(session.token_hash.encode(), payload.encode(), hashlib.sha256).hexdigest()


def remember(db, user, row):
    db.flush()
    db.add(
        InstallationRevision(
            singleton_id=1,
            revision=row.revision,
            actor_id=user.id,
            snapshot=saved(row),
            created_at=row.updated_at,
        )
    )


def operate(db, auth_token, csrf, body, operation):
    current = authority(
        db,
        auth_token,
        csrf,
        "technical_admin",
        exclusive_user=operation == "apply",
        event_prefix="installation",
        scope_lock="installation",
    )
    if isinstance(current, identity.Result):
        return current
    user, session = current
    row = db.scalar(
        select(InstallationConfig)
        .where(InstallationConfig.id == 1)
        .with_for_update(read=operation != "apply")
        .execution_options(populate_existing=True)
    )
    if identity.resolve(db, auth_token, refresh_session=True) is None:
        return identity.denied(db, 401, "installation.session_denied", user=user)
    if row is None:
        return identity.denied(db, 503, "installation.migration_required", user=user)
    if operation == "read":
        audit(db, user, row, "read")
        return identity.Result(200, view(row))
    if operation == "history":
        rows = list(
            db.scalars(
                select(InstallationRevision)
                .where(InstallationRevision.revision > body.after)
                .order_by(InstallationRevision.revision)
                .limit(6)
            )
        )
        audit(db, user, row, "history", returned=min(len(rows), 5))
        return identity.Result(
            200,
            {
                "schema_version": 1,
                "installation_id": str(row.installation_id) if row.installation_id else None,
                "current_revision": row.revision,
                "items": [
                    {
                        "revision": r.revision,
                        "actor_id": str(r.actor_id),
                        "created_at": stamp(r.created_at),
                        "snapshot": r.snapshot,
                    }
                    for r in rows[:5]
                ],
                "next_cursor": rows[4].revision if len(rows) > 5 else None,
            },
        )
    if (
        row.revision != body.expected_revision
        or row.installation_id != body.expected_installation_id
    ):
        return identity.denied(db, 409, "installation.changed", user=user)
    if operation == "export":
        if row.revision == 0:
            return identity.denied(db, 409, "installation.setup_required", user=user)
        audit(db, user, row, "exported")
        return identity.Result(
            200,
            {
                "schema_version": 1,
                "export_kind": "setup_template",
                "template": row.configuration,
                "managed_copy": False,
            },
        )
    template = body.template.model_dump(mode="json")
    changed = [
        key
        for key, value in template["defaults"].items()
        if not row.configuration or row.configuration["defaults"][key] != value
    ]
    if operation == "preview":
        expiry = min(identity.now_utc() + timedelta(minutes=5), identity.aware(session.expires_at))
        audit(db, user, row, "previewed", changed_count=len(changed))
        return identity.Result(
            200,
            {
                "schema_version": 1,
                "record": saved(row),
                "template": template,
                "changed_fields": changed,
                "creates_identity": row.revision == 0,
                "expires_at": stamp(expiry),
                "preview_token": token(session, row, template, expiry),
            },
        )
    now = identity.now_utc()
    if (
        body.expires_at <= now
        or body.expires_at > now + timedelta(minutes=5)
        or not hmac.compare_digest(
            body.preview_token, token(session, row, template, body.expires_at)
        )
    ):
        return identity.denied(db, 409, "installation.preview_invalid", user=user)
    if not changed:
        audit(db, user, row, "unchanged")
        return identity.Result(200, {**view(row), "changed": False})
    if row.revision >= 100:
        return identity.denied(db, 429, "installation.history_limit", user=user)
    row.installation_id = row.installation_id or uuid4()
    row.configuration = template
    row.revision += 1
    row.updated_by = user.id
    row.updated_at = now
    remember(db, user, row)
    audit(db, user, row, "applied", changed_count=len(changed))
    return identity.Result(200, {**view(row), "changed": True})
