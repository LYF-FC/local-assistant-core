from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app import routine_contracts as contract
from app import routines
from app.auth_routes import get_db
from app.manual_tasks import Scoped
from app.task_routes import execute

router = APIRouter(prefix="/api/v1/routines", tags=["recurring routines"])


@router.post("/preview")
def preview(body: contract.Values, request: Request, db: Annotated[Session, Depends(get_db)]):
    return execute(db, request, lambda token, csrf: routines.preview(db, token, csrf, body))


@router.post("")
def create(body: contract.Save, request: Request, db: Annotated[Session, Depends(get_db)]):
    return execute(db, request, lambda token, csrf: routines.create(db, token, csrf, body))


@router.post("/query")
def query(body: contract.Query, request: Request, db: Annotated[Session, Depends(get_db)]):
    return execute(db, request, lambda token, csrf: routines.listing(db, token, csrf, body))


@router.post("/{identifier}/read")
def read(identifier: UUID, body: Scoped, request: Request, db: Annotated[Session, Depends(get_db)]):
    return execute(
        db, request, lambda token, csrf: routines.operate(db, token, csrf, identifier, body, "read")
    )


@router.post("/{identifier}/correct")
def correct(
    identifier: UUID,
    body: contract.Correct,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
):
    return execute(
        db,
        request,
        lambda token, csrf: routines.operate(db, token, csrf, identifier, body, "correct"),
    )


@router.post("/{identifier}/action")
def action(
    identifier: UUID,
    body: contract.Action,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
):
    return execute(
        db,
        request,
        lambda token, csrf: routines.operate(db, token, csrf, identifier, body, "action"),
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
        lambda token, csrf: routines.operate(db, token, csrf, identifier, body, "history"),
    )


@router.post("/{identifier}/occurrences")
def occurrences(
    identifier: UUID,
    body: contract.Occurrences,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
):
    return execute(
        db,
        request,
        lambda token, csrf: routines.operate(db, token, csrf, identifier, body, "occurrences"),
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
        lambda token, csrf: routines.operate(db, token, csrf, identifier, body, "export"),
    )
    if response.status_code == 200:
        response.headers["Content-Disposition"] = (
            'attachment; filename="butler-routine-page-v1.json"'
        )
    return response
