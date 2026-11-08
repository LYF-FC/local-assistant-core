from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy.orm import Session

from app import context_preview, identity
from app.auth_routes import get_db, run

router = APIRouter(prefix="/api/v1/context", tags=["context-preview"])


class Selection(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: UUID
    expected_revision: int = Field(strict=True, ge=1)


class Preview(BaseModel):
    model_config = ConfigDict(extra="forbid")
    scope: str = Field(min_length=1, max_length=96)
    selections: list[Selection] = Field(min_length=1, max_length=10)
    max_bytes: int = Field(strict=True, ge=512, le=16384, default=8192)

    @model_validator(mode="after")
    def unique_ids(self):
        if len({item.id for item in self.selections}) != len(self.selections):
            raise ValueError("Selections must be unique")
        return self


@router.get("/candidates")
def catalogue(
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    scope: Annotated[str, Query(min_length=1, max_length=96)],
    after: UUID | None = None,
    limit: Annotated[int, Query(ge=1, le=25)] = 25,
):
    result = run(
        db,
        request,
        lambda: context_preview.catalogue(
            db, request.cookies.get(identity.COOKIE), scope, after, limit
        ),
    )
    return JSONResponse(result.payload, status_code=result.status)


@router.post("/preview")
def preview(body: Preview, request: Request, db: Annotated[Session, Depends(get_db)]):
    result = run(
        db,
        request,
        lambda: context_preview.preview(
            db,
            request.cookies.get(identity.COOKIE),
            request.headers.get("x-csrf-token"),
            body.scope,
            body.selections,
            body.max_bytes,
        ),
        unsafe=True,
    )
    return JSONResponse(result.payload, status_code=result.status)
