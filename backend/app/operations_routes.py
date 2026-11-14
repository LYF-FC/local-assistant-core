from typing import Annotated

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app import operations
from app.auth_routes import get_db
from app.document_routes import execute

router = APIRouter(prefix="/api/v1/operations", tags=["operations observations"])


@router.post("/read")
def read(body: operations.Read, request: Request, db: Annotated[Session, Depends(get_db)]):
    return execute(db, request, lambda token, csrf: operations.read(db, token, csrf, body))


@router.post("/audit-summary")
def audit_summary(
    body: operations.AuditSummaryRead,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
):
    return execute(db, request, lambda token, csrf: operations.audit_summary(db, token, csrf, body))
