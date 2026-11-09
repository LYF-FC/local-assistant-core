from typing import Annotated

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app import installation
from app.auth_routes import get_db
from app.document_routes import execute

router = APIRouter(prefix="/api/v1/installation", tags=["installation setup"])


@router.post("/read")
def read(body: installation.Admin, request: Request, db: Annotated[Session, Depends(get_db)]):
    return execute(
        db, request, lambda token, csrf: installation.operate(db, token, csrf, body, "read")
    )


@router.post("/preview")
def preview(body: installation.Preview, request: Request, db: Annotated[Session, Depends(get_db)]):
    return execute(
        db, request, lambda token, csrf: installation.operate(db, token, csrf, body, "preview")
    )


@router.post("/apply")
def apply(body: installation.Apply, request: Request, db: Annotated[Session, Depends(get_db)]):
    return execute(
        db, request, lambda token, csrf: installation.operate(db, token, csrf, body, "apply")
    )


@router.post("/history")
def history(body: installation.History, request: Request, db: Annotated[Session, Depends(get_db)]):
    return execute(
        db, request, lambda token, csrf: installation.operate(db, token, csrf, body, "history")
    )


@router.post("/export")
def export(body: installation.Export, request: Request, db: Annotated[Session, Depends(get_db)]):
    response = execute(
        db, request, lambda token, csrf: installation.operate(db, token, csrf, body, "export")
    )
    if response.status_code == 200:
        response.headers["Content-Disposition"] = (
            'attachment; filename="butler-setup-template-v1.json"'
        )
    return response
