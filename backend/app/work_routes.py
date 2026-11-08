from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app import (
    identity,
    work_access,
    work_capture,
    work_confirmation,
    work_context,
    work_interface,
    work_notes,
    work_read,
    work_review,
)
from app.auth_routes import get_db, run

router = APIRouter(prefix="/api/v1/work/workspaces", tags=["work-access-registry"])


@router.get("")
def list_workspaces(
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    after: UUID | None = None,
    limit: Annotated[int, Query(ge=1, le=25)] = 25,
):
    result = run(
        db,
        request,
        lambda: work_access.inspect_work(
            db, request.cookies.get(identity.COOKIE), after=after, limit=limit
        ),
    )
    return JSONResponse(result.payload, status_code=result.status)


@router.post("/{workspace_id}/drafts/{record_id}/preview")
def preview_draft(
    workspace_id: UUID,
    record_id: UUID,
    body: work_review.Preview,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    engines: Annotated[work_read.EngineSource | None, Depends(work_review.get_review_engines)],
):
    result = run(
        db,
        request,
        lambda: work_review.prepare(
            db,
            request.cookies.get(identity.COOKIE),
            request.headers.get("x-csrf-token"),
            workspace_id,
            record_id,
            engines,
        ),
        unsafe=True,
    )
    return JSONResponse(result.payload, status_code=result.status)


@router.post("/{workspace_id}/drafts/{record_id}/review")
def review_draft(
    workspace_id: UUID,
    record_id: UUID,
    body: work_review.Review,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    engines: Annotated[work_read.EngineSource | None, Depends(work_review.get_review_engines)],
):
    result = run(
        db,
        request,
        lambda: work_review.prepare(
            db,
            request.cookies.get(identity.COOKIE),
            request.headers.get("x-csrf-token"),
            workspace_id,
            record_id,
            engines,
            body,
        ),
        unsafe=True,
    )
    return JSONResponse(result.payload, status_code=result.status)


@router.get("/{workspace_id}/status")
def workspace_status(workspace_id: UUID, request: Request, db: Annotated[Session, Depends(get_db)]):
    result = run(
        db,
        request,
        lambda: work_access.inspect_work(db, request.cookies.get(identity.COOKIE), workspace_id),
    )
    return JSONResponse(result.payload, status_code=result.status)


class ValidationRead(BaseModel):
    model_config = ConfigDict(extra="forbid")
    limit: int = Field(strict=True, ge=1, le=25, default=10)


@router.post("/{workspace_id}/validation-read")
def validation_read(
    workspace_id: UUID,
    body: ValidationRead,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    engines: Annotated[work_read.EngineSource | None, Depends(work_read.get_work_engines)],
):
    result = run(
        db,
        request,
        lambda: work_read.read_validation(
            db,
            request.cookies.get(identity.COOKIE),
            request.headers.get("x-csrf-token"),
            workspace_id,
            body.limit,
            engines,
        ),
        unsafe=True,
    )
    return JSONResponse(result.payload, status_code=result.status)


@router.post("/{workspace_id}/drafts/{record_id}/confirm")
def confirm_draft(
    workspace_id: UUID,
    record_id: UUID,
    body: work_confirmation.Confirmation,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    engines: Annotated[
        work_read.EngineSource | None, Depends(work_confirmation.get_confirmation_engines)
    ],
):
    result = run(
        db,
        request,
        lambda: work_confirmation.request_confirmation(
            db,
            request.cookies.get(identity.COOKIE),
            request.headers.get("x-csrf-token"),
            workspace_id,
            record_id,
            engines,
            body=body,
        ),
        unsafe=True,
    )
    return JSONResponse(result.payload, status_code=result.status)


@router.post("/{workspace_id}/confirmations/{command_id}/status")
def confirmation_status(
    workspace_id: UUID,
    command_id: UUID,
    body: work_review.Preview,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    engines: Annotated[
        work_read.EngineSource | None, Depends(work_confirmation.get_confirmation_engines)
    ],
):
    result = run(
        db,
        request,
        lambda: work_confirmation.request_confirmation(
            db,
            request.cookies.get(identity.COOKIE),
            request.headers.get("x-csrf-token"),
            workspace_id,
            None,
            engines,
            command=command_id,
        ),
        unsafe=True,
    )
    return JSONResponse(result.payload, status_code=result.status)


@router.post("/{workspace_id}/context/preview")
def preview_work_context(
    workspace_id: UUID,
    body: work_context.Preview,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    engines: Annotated[work_read.EngineSource | None, Depends(work_context.get_context_engines)],
):
    result = run(
        db,
        request,
        lambda: work_context.preview(
            db,
            request.cookies.get(identity.COOKIE),
            request.headers.get("x-csrf-token"),
            workspace_id,
            body,
            engines,
        ),
        unsafe=True,
    )
    return JSONResponse(result.payload, status_code=result.status)


@router.post("/{workspace_id}/captures")
def prepare_capture(
    workspace_id: UUID,
    body: work_capture.Capture,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    engines: Annotated[work_read.EngineSource | None, Depends(work_capture.get_capture_engines)],
):
    outcome = run(
        db,
        request,
        lambda: work_capture.prepare(
            db,
            request.cookies.get(identity.COOKIE),
            request.headers.get("x-csrf-token"),
            workspace_id,
            engines,
            body=body,
        ),
        unsafe=True,
    )
    return JSONResponse(outcome.payload, status_code=outcome.status)


@router.post("/{workspace_id}/captures/{command_id}/status")
def capture_status(
    workspace_id: UUID,
    command_id: UUID,
    body: work_review.Preview,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    engines: Annotated[work_read.EngineSource | None, Depends(work_capture.get_capture_engines)],
):
    outcome = run(
        db,
        request,
        lambda: work_capture.prepare(
            db,
            request.cookies.get(identity.COOKIE),
            request.headers.get("x-csrf-token"),
            workspace_id,
            engines,
            command=command_id,
        ),
        unsafe=True,
    )
    return JSONResponse(outcome.payload, status_code=outcome.status)


@router.post("/{workspace_id}/drafts/{record_id}/correct")
def correct_note(
    workspace_id: UUID,
    record_id: UUID,
    body: work_notes.Correct,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    engines: Annotated[work_read.EngineSource | None, Depends(work_notes.get_change_engines)],
):
    outcome = run(
        db,
        request,
        lambda: work_notes.prepare(
            db,
            request.cookies.get(identity.COOKIE),
            request.headers.get("x-csrf-token"),
            workspace_id,
            engines,
            target=record_id,
            body=body,
        ),
        unsafe=True,
    )
    return JSONResponse(outcome.payload, status_code=outcome.status)


@router.post("/{workspace_id}/drafts/{record_id}/forget")
def forget_note(
    workspace_id: UUID,
    record_id: UUID,
    body: work_notes.Forget,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    engines: Annotated[work_read.EngineSource | None, Depends(work_notes.get_change_engines)],
):
    outcome = run(
        db,
        request,
        lambda: work_notes.prepare(
            db,
            request.cookies.get(identity.COOKIE),
            request.headers.get("x-csrf-token"),
            workspace_id,
            engines,
            target=record_id,
            body=body,
        ),
        unsafe=True,
    )
    return JSONResponse(outcome.payload, status_code=outcome.status)


@router.post("/{workspace_id}/note-changes/{command_id}/status")
def note_change_status(
    workspace_id: UUID,
    command_id: UUID,
    body: work_review.Preview,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    engines: Annotated[work_read.EngineSource | None, Depends(work_notes.get_change_engines)],
):
    outcome = run(
        db,
        request,
        lambda: work_notes.prepare(
            db,
            request.cookies.get(identity.COOKIE),
            request.headers.get("x-csrf-token"),
            workspace_id,
            engines,
            command=command_id,
        ),
        unsafe=True,
    )
    return JSONResponse(outcome.payload, status_code=outcome.status)


@router.post("/{workspace_id}/notes/catalogue")
def notes_catalogue(
    workspace_id: UUID,
    body: work_interface.Catalogue,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    engines: Annotated[
        work_read.EngineSource | None, Depends(work_interface.get_interface_engines)
    ],
):
    outcome = run(
        db,
        request,
        lambda: work_interface.read(
            db,
            request.cookies.get(identity.COOKIE),
            request.headers.get("x-csrf-token"),
            workspace_id,
            engines,
            body=body,
        ),
        unsafe=True,
    )
    return JSONResponse(outcome.payload, status_code=outcome.status)


@router.post("/{workspace_id}/notes/{record_id}/inspect")
def inspect_note(
    workspace_id: UUID,
    record_id: UUID,
    body: work_review.Preview,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    engines: Annotated[
        work_read.EngineSource | None, Depends(work_interface.get_interface_engines)
    ],
):
    outcome = run(
        db,
        request,
        lambda: work_interface.read(
            db,
            request.cookies.get(identity.COOKIE),
            request.headers.get("x-csrf-token"),
            workspace_id,
            engines,
            record=record_id,
        ),
        unsafe=True,
    )
    return JSONResponse(outcome.payload, status_code=outcome.status)


@router.post("/{workspace_id}/notes/export")
def export_notes(
    workspace_id: UUID,
    body: work_interface.Export,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    engines: Annotated[work_read.EngineSource | None, Depends(work_interface.get_export_engines)],
):
    outcome = run(
        db,
        request,
        lambda: work_interface.read(
            db,
            request.cookies.get(identity.COOKIE),
            request.headers.get("x-csrf-token"),
            workspace_id,
            engines,
            export_body=body,
        ),
        unsafe=True,
    )
    if outcome.status == 200 and identity.now_utc() >= datetime.fromisoformat(
        outcome.payload["valid_until"]
    ):
        return JSONResponse({"detail": "Export preview expired"}, status_code=409)
    return JSONResponse(outcome.payload, status_code=outcome.status)
