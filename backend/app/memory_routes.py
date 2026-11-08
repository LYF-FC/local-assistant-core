from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import JSONResponse
from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, JsonValue
from sqlalchemy.orm import Session

from app import identity, memory
from app.auth_routes import get_db, run

router = APIRouter(prefix="/api/v1/memory", tags=["memory"])
Kind = Literal["profile", "preference", "experience", "procedure", "context"]


class Content(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str = Field(min_length=1, max_length=160)
    content: dict[str, JsonValue]
    source_type: Literal["manual", "document", "conversation", "feedback"]
    source_reference: str = Field(min_length=1, max_length=512)
    assessment: Literal["confirmed", "tentative"]
    expires_at: AwareDatetime | None = None


class Create(Content):
    scope: str = Field(min_length=1, max_length=96)
    kind: Kind


class Correct(Content):
    expected_revision: int = Field(strict=True, ge=1)


class Forget(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_revision: int = Field(strict=True, ge=1)


@router.post("")
def create(body: Create, request: Request, db: Annotated[Session, Depends(get_db)]):
    outcome = run(
        db,
        request,
        lambda: memory.create(
            db,
            request.cookies.get(identity.COOKIE),
            request.headers.get("x-csrf-token"),
            body.scope,
            body.kind,
            body.model_dump(exclude={"scope", "kind"}),
        ),
        unsafe=True,
    )
    return JSONResponse(outcome.payload, status_code=outcome.status)


@router.get("")
@router.get("/export")
def listing(
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    after: UUID | None = None,
    limit: Annotated[int, Query(ge=1, le=50)] = 25,
    scope: str | None = None,
    kind: Kind | None = None,
    include_expired: bool = False,
    include_forgotten: bool = False,
):
    export = request.url.path.endswith("/export")
    outcome = run(
        db,
        request,
        lambda: memory.listing(
            db,
            request.cookies.get(identity.COOKIE),
            after=after,
            limit=limit,
            scope=scope,
            kind=kind,
            include_expired=include_expired,
            include_forgotten=include_forgotten,
            export=export,
        ),
    )
    headers = (
        {"Content-Disposition": 'attachment; filename="butler-memory-v1.json"'}
        if export and outcome.status == 200
        else {}
    )
    return JSONResponse(outcome.payload, status_code=outcome.status, headers=headers)


@router.get("/{identifier}")
def read(
    identifier: UUID,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    include_expired: bool = False,
):
    outcome = run(
        db,
        request,
        lambda: memory.operate(
            db,
            request.cookies.get(identity.COOKIE),
            None,
            identifier,
            include_expired=include_expired,
        ),
    )
    return JSONResponse(outcome.payload, status_code=outcome.status)


@router.get("/{identifier}/history")
def history(
    identifier: UUID,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    after: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=50)] = 25,
):
    outcome = run(
        db,
        request,
        lambda: memory.operate(
            db,
            request.cookies.get(identity.COOKIE),
            None,
            identifier,
            operation="history",
            after=after,
            limit=limit,
        ),
    )
    return JSONResponse(outcome.payload, status_code=outcome.status)


@router.patch("/{identifier}")
def correct(
    identifier: UUID, body: Correct, request: Request, db: Annotated[Session, Depends(get_db)]
):
    outcome = run(
        db,
        request,
        lambda: memory.operate(
            db,
            request.cookies.get(identity.COOKIE),
            request.headers.get("x-csrf-token"),
            identifier,
            operation="correct",
            expected=body.expected_revision,
            values=body.model_dump(exclude={"expected_revision"}),
        ),
        unsafe=True,
    )
    return JSONResponse(outcome.payload, status_code=outcome.status)


@router.post("/{identifier}/forget")
def forget(
    identifier: UUID, body: Forget, request: Request, db: Annotated[Session, Depends(get_db)]
):
    outcome = run(
        db,
        request,
        lambda: memory.operate(
            db,
            request.cookies.get(identity.COOKIE),
            request.headers.get("x-csrf-token"),
            identifier,
            operation="forget",
            expected=body.expected_revision,
        ),
        unsafe=True,
    )
    return JSONResponse(outcome.payload, status_code=outcome.status)
