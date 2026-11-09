from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app import calendar_contracts as contract
from app import calendars
from app.auth_routes import get_db
from app.manual_tasks import Expected, Scoped
from app.task_routes import execute

router = APIRouter(prefix="/api/v1/calendars", tags=["calendar snapshots"])


@router.post("")
def create(body: contract.Create, request: Request, db: Annotated[Session, Depends(get_db)]):
    return execute(db, request, lambda token, csrf: calendars.create(db, token, csrf, body))


@router.post("/query")
def query(body: contract.Query, request: Request, db: Annotated[Session, Depends(get_db)]):
    return execute(db, request, lambda token, csrf: calendars.listing(db, token, csrf, body))


@router.post("/briefing")
def briefing(body: contract.Briefing, request: Request, db: Annotated[Session, Depends(get_db)]):
    return execute(db, request, lambda token, csrf: calendars.briefing(db, token, csrf, body))


# Explicit typed routes keep validation ahead of the transaction boundary.
@router.post("/{identifier}/read")
def read(identifier: UUID, body: Scoped, request: Request, db: Annotated[Session, Depends(get_db)]):
    return execute(
        db,
        request,
        lambda token, csrf: calendars.operate(db, token, csrf, identifier, body, "read"),
    )


@router.post("/{identifier}/import")
def ingest(
    identifier: UUID,
    body: contract.Import,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
):
    return execute(
        db,
        request,
        lambda token, csrf: calendars.operate(db, token, csrf, identifier, body, "import"),
    )


@router.post("/{identifier}/unavailable")
def unavailable(
    identifier: UUID,
    body: contract.Unavailable,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
):
    return execute(
        db,
        request,
        lambda token, csrf: calendars.operate(db, token, csrf, identifier, body, "unavailable"),
    )


@router.post("/{identifier}/forget")
def forget(
    identifier: UUID, body: Expected, request: Request, db: Annotated[Session, Depends(get_db)]
):
    return execute(
        db,
        request,
        lambda token, csrf: calendars.operate(db, token, csrf, identifier, body, "forget"),
    )


@router.post("/{identifier}/history")
def history(
    identifier: UUID,
    body: contract.History,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
):
    return execute(
        db,
        request,
        lambda token, csrf: calendars.operate(db, token, csrf, identifier, body, "history"),
    )


@router.post("/{identifier}/export")
def export(
    identifier: UUID,
    body: contract.Export,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
):
    response = execute(
        db,
        request,
        lambda token, csrf: calendars.operate(db, token, csrf, identifier, body, "export"),
    )
    if response.status_code == 200:
        response.headers["Content-Disposition"] = (
            'attachment; filename="butler-calendar-history-v1.json"'
        )
    return response
