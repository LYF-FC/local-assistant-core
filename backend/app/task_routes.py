from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app import identity
from app import manual_tasks as tasks
from app.auth_routes import get_db, run

router = APIRouter(prefix="/api/v1/tasks", tags=["manual tasks"])


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
def create(body: tasks.Create, request: Request, db: Annotated[Session, Depends(get_db)]):
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
        response.headers["Content-Disposition"] = 'attachment; filename="butler-tasks-v1.json"'
    return response


@router.post("/{identifier}/read")
def read(
    identifier: UUID, body: tasks.Read, request: Request, db: Annotated[Session, Depends(get_db)]
):
    return execute(
        db, request, lambda token, csrf: tasks.operate(db, token, csrf, identifier, body, "read")
    )


@router.post("/{identifier}/history")
def history(
    identifier: UUID, body: tasks.History, request: Request, db: Annotated[Session, Depends(get_db)]
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


@router.post("/{identifier}/transition")
def transition(
    identifier: UUID,
    body: tasks.Transition,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
):
    return execute(
        db,
        request,
        lambda token, csrf: tasks.operate(db, token, csrf, identifier, body, "transition"),
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
