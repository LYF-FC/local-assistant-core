from typing import Annotated

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app import document_answers, identity
from app.auth_routes import get_db, run

router = APIRouter(prefix="/api/v1/document-answers", tags=["document-answers"])


@router.post("")
def answer(
    body: document_answers.Question, request: Request, db: Annotated[Session, Depends(get_db)]
):
    token, csrf = request.cookies.get(identity.COOKIE), request.headers.get("x-csrf-token")
    plan = None

    def prepare():
        nonlocal plan
        outcome, plan = document_answers.prepare(db, token, csrf, body)
        return outcome

    result = run(db, request, prepare, unsafe=True)
    if result.status == 200 and plan is not None:
        result = run(
            db, request, lambda: document_answers.dispatch(db, token, csrf, body, plan), unsafe=True
        )
    return JSONResponse(result.payload, status_code=result.status)
