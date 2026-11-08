from collections.abc import Iterator
from typing import Annotated
from urllib.parse import urlsplit

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app import identity
from app.config import settings
from app.db import SessionLocal

router = APIRouter(prefix="/api/v1/auth", tags=["identity"])


class LoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    slug: str = Field(min_length=1, max_length=64, pattern=r"^[a-z0-9][a-z0-9_-]*$")
    password: SecretStr = Field(min_length=1, max_length=1024)

    @field_validator("password")
    @classmethod
    def password_size(cls, value: SecretStr) -> SecretStr:
        if len(value.get_secret_value().encode()) > 1024:
            raise ValueError("Password input exceeds the byte limit")
        return value


def get_db() -> Iterator[Session]:
    with SessionLocal() as session:
        yield session


def request_guard(db: Session, request: Request, unsafe: bool) -> identity.Result | None:
    if request.url.scheme != "https":
        return identity.denied(db, 400, "auth.tls_required")
    if request.url.netloc != urlsplit(settings.auth_origin).netloc:
        return identity.denied(db, 403, "auth.host_denied")
    if unsafe and request.headers.get("origin") != settings.auth_origin:
        return identity.denied(db, 403, "auth.origin_denied")
    return None


def run(db: Session, request: Request, operation, unsafe=False) -> identity.Result:
    try:
        with db.begin():
            rejection = request_guard(db, request, unsafe)
            outcome = rejection or operation()
        # Do not release a token or protected response until audit and state commit.
        return outcome
    except SQLAlchemyError:
        return identity.Result(503, {"detail": "Identity service unavailable"})


@router.post("/login")
def login(body: LoginRequest, request: Request, db: Annotated[Session, Depends(get_db)]):
    outcome = run(
        db,
        request,
        lambda: identity.login(
            db,
            body.slug,
            body.password.get_secret_value(),
            request.client.host if request.client else "unknown",
            request.cookies.get(identity.COOKIE),
        ),
        unsafe=True,
    )
    response = JSONResponse(outcome.payload, status_code=outcome.status)
    if outcome.token:
        response.set_cookie(
            identity.COOKIE,
            outcome.token,
            secure=True,
            httponly=True,
            samesite="strict",
            path="/",
            max_age=int(identity.SESSION_LIFETIME.total_seconds()),
        )
    if outcome.status == 429:
        response.headers["Retry-After"] = str(int(identity.RATE_WINDOW.total_seconds()))
    return response


@router.get("/me")
def me(request: Request, db: Annotated[Session, Depends(get_db)]):
    outcome = run(
        db, request, lambda: identity.inspect_identity(db, request.cookies.get(identity.COOKIE))
    )
    return JSONResponse(outcome.payload, status_code=outcome.status)


@router.get("/scopes/{scope}")
def scope_access(scope: str, request: Request, db: Annotated[Session, Depends(get_db)]):
    outcome = run(
        db,
        request,
        lambda: identity.inspect_identity(db, request.cookies.get(identity.COOKIE), scope),
    )
    return JSONResponse(outcome.payload, status_code=outcome.status)


@router.post("/logout")
def logout(request: Request, db: Annotated[Session, Depends(get_db)]):
    outcome = run(
        db,
        request,
        lambda: identity.logout(
            db, request.cookies.get(identity.COOKIE), request.headers.get("x-csrf-token")
        ),
        unsafe=True,
    )
    response = JSONResponse(outcome.payload, status_code=outcome.status)
    if outcome.status == 200:
        response.delete_cookie(
            identity.COOKIE, path="/", secure=True, httponly=True, samesite="strict"
        )
    return response


class BootstrapRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")


@router.post("/session")
def bootstrap(body: BootstrapRequest, request: Request, db: Annotated[Session, Depends(get_db)]):
    # Reload bootstrap cannot require the CSRF value that existed only in the old
    # page's memory. Exact Origin + JSON + session cookie protect this boundary.
    def operation():
        if request.headers.get("content-type", "").split(";")[0].strip() != "application/json":
            return identity.denied(db, 403, "auth.bootstrap_type_denied")
        return identity.bootstrap_session(db, request.cookies.get(identity.COOKIE))

    outcome = run(db, request, operation, unsafe=True)
    return JSONResponse(outcome.payload, status_code=outcome.status)
