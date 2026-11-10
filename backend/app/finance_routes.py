import json
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse, Response
from sqlalchemy.orm import Session

from app import finance as tasks
from app import finance_contracts as contract
from app import identity
from app.auth_routes import get_db, run

router = APIRouter(prefix="/api/v1/finance", tags=["financial records"])


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
def create(body: contract.Create, request: Request, db: Annotated[Session, Depends(get_db)]):
    return execute(db, request, lambda token, csrf: tasks.create(db, token, csrf, body))


@router.post("/query")
def query(body: contract.Query, request: Request, db: Annotated[Session, Depends(get_db)]):
    return execute(db, request, lambda token, csrf: tasks.listing(db, token, csrf, body))


@router.post("/export")
def export(body: contract.Export, request: Request, db: Annotated[Session, Depends(get_db)]):
    response = execute(
        db, request, lambda token, csrf: tasks.listing(db, token, csrf, body, export=True)
    )
    if response.status_code == 200:
        response.headers["Content-Disposition"] = 'attachment; filename="butler-finance-v1.json"'
    return download(response, body.format)


@router.post("/{identifier}/read")
def read(
    identifier: UUID,
    body: contract.Scoped,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
):
    return execute(
        db, request, lambda token, csrf: tasks.operate(db, token, csrf, identifier, body, "read")
    )


@router.post("/{identifier}/history")
def history(
    identifier: UUID,
    body: contract.History,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
):
    return execute(
        db, request, lambda token, csrf: tasks.operate(db, token, csrf, identifier, body, "history")
    )


@router.post("/{identifier}/correct")
def correct(
    identifier: UUID,
    body: contract.Correct,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
):
    return execute(
        db, request, lambda token, csrf: tasks.operate(db, token, csrf, identifier, body, "correct")
    )


@router.post("/{identifier}/accept")
def accept(
    identifier: UUID,
    body: contract.Accept,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
):
    return execute(
        db,
        request,
        lambda token, csrf: tasks.operate(db, token, csrf, identifier, body, "accept"),
    )


@router.post("/{identifier}/forget")
def forget(
    identifier: UUID,
    body: contract.Expected,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
):
    return execute(
        db, request, lambda token, csrf: tasks.operate(db, token, csrf, identifier, body, "forget")
    )


def download(response, format):
    if response.status_code != 200 or format == "json":
        return response
    text = (
        "# Financial capture — unmanaged copy\n\nRecorded inputs are not financial advice or execution authority.\n\n```json\n"
        + json.dumps(json.loads(response.body), ensure_ascii=False, indent=2)
        + "\n```\n"
    )
    return Response(
        text,
        media_type="text/markdown",
        headers={
            "Content-Disposition": 'attachment; filename="butler-finance-v1.md"',
            "Cache-Control": "no-store",
        },
    )


@router.post("/{identifier}/export")
def export_record(
    identifier: UUID,
    body: contract.RecordExport,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
):
    response = execute(
        db, request, lambda token, csrf: tasks.operate(db, token, csrf, identifier, body, "export")
    )
    if response.status_code == 200:
        response.headers["Content-Disposition"] = (
            'attachment; filename="butler-finance-history-v1.json"'
        )
    return download(response, body.format)
