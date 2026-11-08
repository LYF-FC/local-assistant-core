from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app import identity, jobs
from app.auth_routes import get_db, run

router = APIRouter(prefix="/api/v1/jobs", tags=["jobs"])


class EnqueueRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    approval_id: UUID
    payload_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    policy_version: str = Field(min_length=1, max_length=64)
    idempotency_key: str = Field(min_length=16, max_length=128, pattern=r"^[A-Za-z0-9_-]+$")


@router.post("")
def enqueue(body: EnqueueRequest, request: Request, db: Annotated[Session, Depends(get_db)]):
    outcome = run(
        db,
        request,
        lambda: jobs.enqueue(
            db,
            request.cookies.get(identity.COOKIE),
            request.headers.get("x-csrf-token"),
            body.approval_id,
            body.payload_hash,
            body.policy_version,
            body.idempotency_key,
        ),
        unsafe=True,
    )
    return JSONResponse(outcome.payload, status_code=outcome.status)


@router.get("/{identifier}")
def read(identifier: UUID, request: Request, db: Annotated[Session, Depends(get_db)]):
    outcome = run(
        db,
        request,
        lambda: jobs.inspect_job(db, request.cookies.get(identity.COOKIE), None, identifier),
    )
    return JSONResponse(outcome.payload, status_code=outcome.status)


@router.post("/{identifier}/review")
def review(identifier: UUID, request: Request, db: Annotated[Session, Depends(get_db)]):
    outcome = run(
        db,
        request,
        lambda: jobs.inspect_job(
            db,
            request.cookies.get(identity.COOKIE),
            request.headers.get("x-csrf-token"),
            identifier,
            True,
        ),
        unsafe=True,
    )
    return JSONResponse(outcome.payload, status_code=outcome.status)
