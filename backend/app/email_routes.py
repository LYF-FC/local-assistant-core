from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app import email_intake
from app.auth_routes import get_db
from app.document_routes import execute

router = APIRouter(prefix="/api/v1/email-intake", tags=["offline email intake"])


@router.post("")
def ingest(body: email_intake.Import, request: Request, db: Annotated[Session, Depends(get_db)]):
    return execute(db, request, lambda token, csrf: email_intake.ingest(db, token, csrf, body))


@router.post("/{identifier}/read")
def read(
    identifier: UUID,
    body: email_intake.Read,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
):
    return execute(
        db, request, lambda token, csrf: email_intake.operate(db, token, csrf, identifier, body)
    )


@router.post("/{identifier}/export")
def export(
    identifier: UUID,
    body: email_intake.Export,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
):
    response = execute(
        db,
        request,
        lambda token, csrf: email_intake.operate(db, token, csrf, identifier, body, True),
    )
    if response.status_code == 200:
        response.headers["Content-Disposition"] = (
            'attachment; filename="butler-original-email-v1.json"'
        )
    return response
