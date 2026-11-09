from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app import invoice_review as invoices
from app.auth_routes import get_db
from app.document_routes import execute
from app.manual_tasks import Scoped

router = APIRouter(prefix="/api/v1/invoices", tags=["invoice review"])


@router.post("/{identifier}/read")
def read(identifier: UUID, body: Scoped, request: Request, db: Annotated[Session, Depends(get_db)]):
    return execute(
        db, request, lambda token, csrf: invoices.operate(db, token, csrf, identifier, body, "read")
    )


@router.post("/{identifier}/prepare")
def prepare(
    identifier: UUID,
    body: invoices.Expected,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
):
    return execute(
        db,
        request,
        lambda token, csrf: invoices.operate(db, token, csrf, identifier, body, "prepare"),
    )


@router.post("/{identifier}/review")
def review(
    identifier: UUID,
    body: invoices.Confirm,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
):
    return execute(
        db,
        request,
        lambda token, csrf: invoices.operate(db, token, csrf, identifier, body, "review"),
    )


@router.post("/{identifier}/forget")
def forget(
    identifier: UUID,
    body: invoices.Expected,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
):
    return execute(
        db,
        request,
        lambda token, csrf: invoices.operate(db, token, csrf, identifier, body, "forget"),
    )


@router.post("/{identifier}/duplicates")
def duplicates(
    identifier: UUID,
    body: invoices.Duplicates,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
):
    return execute(
        db,
        request,
        lambda token, csrf: invoices.operate(db, token, csrf, identifier, body, "duplicates"),
    )


@router.post("/{identifier}/history")
def history(
    identifier: UUID,
    body: invoices.History,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
):
    return execute(
        db,
        request,
        lambda token, csrf: invoices.operate(db, token, csrf, identifier, body, "history"),
    )


@router.post("/{identifier}/export")
def export(
    identifier: UUID,
    body: invoices.Export,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
):
    response = execute(
        db,
        request,
        lambda token, csrf: invoices.operate(db, token, csrf, identifier, body, "export"),
    )
    if response.status_code == 200:
        response.headers["Content-Disposition"] = (
            'attachment; filename="butler-invoice-history-v1.json"'
        )
    return response


@router.post("/{identifier}/plan")
def plan(
    identifier: UUID, body: invoices.Plan, request: Request, db: Annotated[Session, Depends(get_db)]
):
    return execute(
        db, request, lambda token, csrf: invoices.operate(db, token, csrf, identifier, body, "plan")
    )


@router.post("/{identifier}/approve_plan")
def approve_plan(
    identifier: UUID,
    body: invoices.ApprovePlan,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
):
    return execute(
        db,
        request,
        lambda token, csrf: invoices.operate(db, token, csrf, identifier, body, "approve_plan"),
    )


@router.post("/{identifier}/withdraw_plan")
def withdraw_plan(
    identifier: UUID,
    body: invoices.Expected,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
):
    return execute(
        db,
        request,
        lambda token, csrf: invoices.operate(db, token, csrf, identifier, body, "withdraw_plan"),
    )
