from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, JsonValue
from sqlalchemy.orm import Session

from app import approvals, identity
from app import manual_tasks as tasks
from app.auth_routes import get_db, run

router = APIRouter(prefix="/api/v1/approvals", tags=["approvals"])
DB = Annotated[Session, Depends(get_db)]


class CreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    scope: str = Field(min_length=1, max_length=96)
    action_type: Literal["validation.noop"] = "validation.noop"
    payload: dict[str, JsonValue]
    expires_in: int = Field(default=900, ge=60, le=3600, strict=True)


class BindingRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    payload_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    policy_version: str = Field(min_length=1, max_length=64)


class QueryRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    scope: tasks.Scope
    after: UUID | None = None


class DecisionRequest(BindingRequest):
    decision: Literal["approve", "reject"]


def perform(request, db, operation, unsafe=True):
    result = run(db, request, operation, unsafe=unsafe)
    return JSONResponse(result.payload, status_code=result.status)


def credentials(request):
    return request.cookies.get(identity.COOKIE), request.headers.get("x-csrf-token")


@router.post("")
def create(body: CreateRequest, request: Request, db: DB):
    token, csrf = credentials(request)
    return perform(
        request,
        db,
        lambda: approvals.create(
            db, token, csrf, body.scope, body.payload, body.expires_in, body.action_type
        ),
    )


@router.post("/query")
def query(body: QueryRequest, request: Request, db: DB):
    token, csrf = credentials(request)
    return perform(request, db, lambda: approvals.listing(db, token, csrf, body.scope, body.after))


@router.get("/{identifier}")
def read(identifier: UUID, request: Request, db: DB):
    token, csrf = credentials(request)
    return perform(
        request, db, lambda: approvals.operate(db, token, csrf, identifier), unsafe=False
    )


@router.post("/{identifier}/decide")
def decide(identifier: UUID, body: DecisionRequest, request: Request, db: DB):
    token, csrf = credentials(request)
    return perform(
        request,
        db,
        lambda: approvals.operate(
            db, token, csrf, identifier, body.decision, body.payload_hash, body.policy_version
        ),
    )


@router.post("/{identifier}/cancel")
def cancel(identifier: UUID, body: BindingRequest, request: Request, db: DB):
    token, csrf = credentials(request)
    return perform(
        request,
        db,
        lambda: approvals.operate(
            db, token, csrf, identifier, "cancel", body.payload_hash, body.policy_version
        ),
    )


@router.post("/{identifier}/consume")
def consume(identifier: UUID, body: BindingRequest, request: Request, db: DB):
    token, csrf = credentials(request)
    return perform(
        request,
        db,
        lambda: approvals.operate(
            db, token, csrf, identifier, "consume", body.payload_hash, body.policy_version
        ),
    )
