from typing import Annotated

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app import notifications
from app.auth_routes import get_db
from app.task_routes import execute

router = APIRouter(prefix="/api/v1/notifications", tags=["synthetic notifications"])


@router.post("/query")
def query(body: notifications.Query, request: Request, db: Annotated[Session, Depends(get_db)]):
    return execute(db, request, lambda token, csrf: notifications.listing(db, token, csrf, body))


@router.post("/history")
def history(body: notifications.History, request: Request, db: Annotated[Session, Depends(get_db)]):
    return execute(db, request, lambda token, csrf: notifications.history(db, token, csrf, body))
