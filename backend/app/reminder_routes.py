from typing import Annotated

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app import task_reminders as reminders
from app.auth_routes import get_db
from app.manual_tasks import Scoped
from app.task_routes import execute

router = APIRouter(prefix="/api/v1/reminders", tags=["private reminders"])


@router.post("/read")
def read(body: reminders.TaskRequest, request: Request, db: Annotated[Session, Depends(get_db)]):
    return execute(
        db, request, lambda token, csrf: reminders.operate(db, token, csrf, body, "read")
    )


@router.post("/schedule")
def schedule(body: reminders.Schedule, request: Request, db: Annotated[Session, Depends(get_db)]):
    return execute(
        db, request, lambda token, csrf: reminders.operate(db, token, csrf, body, "schedule")
    )


@router.post("/action")
def action(body: reminders.Action, request: Request, db: Annotated[Session, Depends(get_db)]):
    return execute(
        db, request, lambda token, csrf: reminders.operate(db, token, csrf, body, "action")
    )


@router.post("/history")
def history(body: reminders.History, request: Request, db: Annotated[Session, Depends(get_db)]):
    return execute(
        db, request, lambda token, csrf: reminders.operate(db, token, csrf, body, "history")
    )


@router.post("/query")
def query(body: reminders.Query, request: Request, db: Annotated[Session, Depends(get_db)]):
    return execute(db, request, lambda token, csrf: reminders.listing(db, token, csrf, body))


@router.post("/export")
def export(body: reminders.Export, request: Request, db: Annotated[Session, Depends(get_db)]):
    response = execute(
        db, request, lambda token, csrf: reminders.listing(db, token, csrf, body, export=True)
    )
    if response.status_code == 200:
        response.headers["Content-Disposition"] = 'attachment; filename="butler-reminders-v1.json"'
    return response


@router.post("/preferences/read")
def preferences_read(body: Scoped, request: Request, db: Annotated[Session, Depends(get_db)]):
    return execute(db, request, lambda token, csrf: reminders.preferences(db, token, csrf, body))


@router.post("/preferences/save")
def preferences_save(
    body: reminders.Policy, request: Request, db: Annotated[Session, Depends(get_db)]
):
    return execute(
        db, request, lambda token, csrf: reminders.preferences(db, token, csrf, body, write=True)
    )
