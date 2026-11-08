from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app import documents as tasks
from app import identity
from app.auth_routes import get_db, run
from app.manual_tasks import History

router = APIRouter(prefix="/api/v1/documents", tags=["documents"])


def execute(db, request, operation):
    outcome = run(
        db,
        request,
        lambda: operation(
            request.cookies.get(identity.COOKIE), request.headers.get("x-csrf-token")
        ),
        unsafe=True,
    )
    return JSONResponse(outcome.payload, status_code=outcome.status)


@router.post("")
def create(body: tasks.Upload, request: Request, db: Annotated[Session, Depends(get_db)]):
    return execute(db, request, lambda token, csrf: tasks.create(db, token, csrf, body))


@router.post("/query")
def query(body: tasks.Query, request: Request, db: Annotated[Session, Depends(get_db)]):
    return execute(db, request, lambda token, csrf: tasks.listing(db, token, csrf, body))


@router.post("/export")
def export(body: tasks.Export, request: Request, db: Annotated[Session, Depends(get_db)]):
    response = execute(
        db, request, lambda token, csrf: tasks.listing(db, token, csrf, body, export=True)
    )
    if response.status_code == 200:
        response.headers["Content-Disposition"] = 'attachment; filename="butler-documents-v1.json"'
    return response


@router.post("/{identifier}/read")
def read(
    identifier: UUID, body: tasks.Scoped, request: Request, db: Annotated[Session, Depends(get_db)]
):
    return execute(
        db, request, lambda token, csrf: tasks.operate(db, token, csrf, identifier, body, "read")
    )


@router.post("/{identifier}/history")
def history(
    identifier: UUID, body: History, request: Request, db: Annotated[Session, Depends(get_db)]
):
    return execute(
        db, request, lambda token, csrf: tasks.operate(db, token, csrf, identifier, body, "history")
    )


@router.post("/{identifier}/correct")
def correct(
    identifier: UUID, body: tasks.Correct, request: Request, db: Annotated[Session, Depends(get_db)]
):
    return execute(
        db, request, lambda token, csrf: tasks.operate(db, token, csrf, identifier, body, "correct")
    )


@router.post("/{identifier}/forget")
def forget(
    identifier: UUID,
    body: tasks.Expected,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
):
    return execute(
        db, request, lambda token, csrf: tasks.operate(db, token, csrf, identifier, body, "forget")
    )


@router.post("/{identifier}/replace")
def replace(
    identifier: UUID, body: tasks.Replace, request: Request, db: Annotated[Session, Depends(get_db)]
):
    return execute(
        db, request, lambda token, csrf: tasks.operate(db, token, csrf, identifier, body, "replace")
    )


@router.post("/{identifier}/original")
def original(
    identifier: UUID,
    body: tasks.Original,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
):
    return execute(
        db,
        request,
        lambda token, csrf: tasks.operate(db, token, csrf, identifier, body, "original"),
    )


@router.post("/{identifier}/excerpt")
def excerpt(
    identifier: UUID, body: tasks.Excerpt, request: Request, db: Annotated[Session, Depends(get_db)]
):
    return execute(
        db, request, lambda token, csrf: tasks.operate(db, token, csrf, identifier, body, "excerpt")
    )


@router.post("/{identifier}/archive/status")
def archive_status(
    identifier: UUID,
    body: tasks.Expected,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
):
    return execute(
        db,
        request,
        lambda token, csrf: tasks.operate(db, token, csrf, identifier, body, "archive_status"),
    )


@router.post("/{identifier}/archive")
def archive_copy(
    identifier: UUID,
    body: tasks.Expected,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
):
    # Never copy bytes until the cleanup obligation AND its audit have committed.
    prepared = execute(
        db,
        request,
        lambda token, csrf: tasks.operate(db, token, csrf, identifier, body, "archive_bind"),
    )
    if prepared.status_code != 200:
        return prepared
    # Re-resolve session, permissions, ownership and revision after the first commit.
    return execute(
        db,
        request,
        lambda token, csrf: tasks.operate(db, token, csrf, identifier, body, "archive_write"),
    )
