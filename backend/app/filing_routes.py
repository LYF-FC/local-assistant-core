from typing import Annotated

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app import filing
from app.auth_routes import get_db
from app.task_routes import execute

router = APIRouter(prefix="/api/v1/filing", tags=["synthetic invoice filing"])


@router.post("/request")
def request_filing(body: filing.Request, request: Request, db: Annotated[Session, Depends(get_db)]):
    return execute(db, request, lambda token, csrf: filing.request(db, token, csrf, body))


@router.post("/cancel")
def cancel(body: filing.Cancel, request: Request, db: Annotated[Session, Depends(get_db)]):
    return execute(db, request, lambda token, csrf: filing.cancel(db, token, csrf, body))


@router.post("/query")
def query(body: filing.Query, request: Request, db: Annotated[Session, Depends(get_db)]):
    return execute(db, request, lambda token, csrf: filing.listing(db, token, csrf, body))


@router.post("/history")
def history(body: filing.History, request: Request, db: Annotated[Session, Depends(get_db)]):
    return execute(db, request, lambda token, csrf: filing.history(db, token, csrf, body))
