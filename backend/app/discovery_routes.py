from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import JSONResponse
from pydantic import Field
from sqlalchemy.orm import Session

from app import discovery, discovery_digest, identity
from app.auth_routes import get_db, run

router = APIRouter(prefix="/api/v1/discovery", tags=["discovery"])


class Create(discovery.Proposal):
    title: str = Field(min_length=1, max_length=160)
    scope: str = Field(min_length=1, max_length=96)


class Idea(discovery.Strict):
    title: str = Field(min_length=1, max_length=160)
    scope: str = Field(min_length=1, max_length=96)
    summary: str = Field(min_length=1, max_length=1000)
    topic: str = Field(default="unclassified", pattern=r"^[a-z0-9][a-z0-9-]{0,63}$")


class Details(discovery.Proposal):
    title: str = Field(min_length=1, max_length=160)
    expected_revision: int = Field(strict=True, ge=1)


class Feedback(discovery.Strict):
    expected_revision: int = Field(strict=True, ge=1)
    choice: discovery.Choice | None
    note: str = Field(max_length=500, default="")


@router.post("")
def create(body: Create, request: Request, db: Annotated[Session, Depends(get_db)]):
    result = run(
        db,
        request,
        lambda: discovery.create(
            db,
            request.cookies.get(identity.COOKIE),
            request.headers.get("x-csrf-token"),
            body.scope,
            body.title,
            discovery.Proposal.model_validate(body.model_dump(exclude={"title", "scope"})),
        ),
        unsafe=True,
    )
    return JSONResponse(result.payload, status_code=result.status)


@router.post("/ideas")
def create_idea(body: Idea, request: Request, db: Annotated[Session, Depends(get_db)]):
    result = run(
        db,
        request,
        lambda: discovery.create(
            db,
            request.cookies.get(identity.COOKIE),
            request.headers.get("x-csrf-token"),
            body.scope,
            body.title,
            body.model_dump(exclude={"title", "scope"}),
            idea=True,
        ),
        unsafe=True,
    )
    return JSONResponse(result.payload, status_code=result.status)


@router.put("/{identifier}/details")
def details(
    identifier: UUID, body: Details, request: Request, db: Annotated[Session, Depends(get_db)]
):
    result = run(
        db,
        request,
        lambda: discovery.operate(
            db,
            request.cookies.get(identity.COOKIE),
            request.headers.get("x-csrf-token"),
            identifier,
            expected=body.expected_revision,
            details=discovery.Proposal.model_validate(
                body.model_dump(exclude={"title", "expected_revision"})
            ),
            title=body.title,
        ),
        unsafe=True,
    )
    return JSONResponse(result.payload, status_code=result.status)


@router.get("")
def listing(
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    limit: Annotated[int, Query(ge=1, le=50)] = 25,
    after: UUID | None = None,
    after_priority: int | None = None,
    include_dismissed: bool = False,
):
    result = run(
        db,
        request,
        lambda: discovery.listing(
            db,
            request.cookies.get(identity.COOKIE),
            limit,
            after,
            after_priority,
            include_dismissed,
        ),
    )
    return JSONResponse(result.payload, status_code=result.status)


class Inbox(discovery.InboxFilters):
    limit: int = Field(default=25, strict=True, ge=1, le=25)
    after: UUID | None = None
    after_priority: int | None = Field(default=None, strict=True)
    include_dismissed: bool = Field(default=False, strict=True)


@router.post("/inbox")
def inbox(body: Inbox, request: Request, db: Annotated[Session, Depends(get_db)]):
    result = run(
        db,
        request,
        lambda: discovery.listing(
            db,
            request.cookies.get(identity.COOKIE),
            body.limit,
            body.after,
            body.after_priority,
            body.include_dismissed,
            discovery.InboxFilters.model_validate(
                body.model_dump(include={"q", "topic", "stage", "interest"})
            ),
            csrf=request.headers.get("x-csrf-token"),
            locked=True,
        ),
        unsafe=True,
    )
    return JSONResponse(result.payload, status_code=result.status)


@router.post("/digest")
def digest(
    body: discovery_digest.Request, request: Request, db: Annotated[Session, Depends(get_db)]
):
    result = run(
        db,
        request,
        lambda: discovery_digest.prepare(
            db,
            request.cookies.get(identity.COOKIE),
            request.headers.get("x-csrf-token"),
            body,
        ),
        unsafe=True,
    )
    result = discovery_digest.release(result)
    return JSONResponse(result.payload, status_code=result.status)


@router.get("/{identifier}")
def read(identifier: UUID, request: Request, db: Annotated[Session, Depends(get_db)]):
    result = run(
        db,
        request,
        lambda: discovery.operate(db, request.cookies.get(identity.COOKIE), None, identifier),
    )
    return JSONResponse(result.payload, status_code=result.status)


@router.put("/{identifier}/feedback")
def feedback(
    identifier: UUID, body: Feedback, request: Request, db: Annotated[Session, Depends(get_db)]
):
    result = run(
        db,
        request,
        lambda: discovery.operate(
            db,
            request.cookies.get(identity.COOKIE),
            request.headers.get("x-csrf-token"),
            identifier,
            body.expected_revision,
            body.choice,
            body.note,
        ),
        unsafe=True,
    )
    return JSONResponse(result.payload, status_code=result.status)
