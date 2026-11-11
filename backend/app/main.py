from fastapi import Depends, FastAPI, HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.answer_routes import router as answer_router
from app.approval_routes import router as approval_router
from app.auth_routes import router as auth_router
from app.calendar_routes import router as calendar_router
from app.config import settings
from app.context_routes import router as context_router
from app.db import SessionLocal
from app.discovery_routes import router as discovery_router
from app.document_routes import router as document_router
from app.email_routes import router as email_router
from app.finance_routes import router as finance_router
from app.installation_routes import router as installation_router
from app.invoice_routes import router as invoice_router
from app.job_routes import router as job_router
from app.memory_routes import router as memory_router
from app.notification_routes import router as notification_router
from app.operations_routes import router as operations_router
from app.reminder_routes import router as reminder_router
from app.routine_routes import router as routine_router
from app.task_routes import router as task_router
from app.work_routes import router as work_router


def require_identity_foundation() -> None:
    # No token/header or environment switch can bypass the unfinished identity gate.
    # Replace only through spec 001's authenticated, audited permission boundary.
    raise HTTPException(status_code=503, detail="Identity foundation is not enabled")


def create_app() -> FastAPI:
    if settings.env in {"staging", "production"}:
        raise RuntimeError(
            "This foundation is development/test only; production gates are incomplete"
        )
    if settings.env == "development" and settings.postgres_user != "butler_runtime":
        raise RuntimeError("The API requires the restricted butler_runtime database role")
    application = FastAPI(
        title="Butler API",
        version=settings.app_version,
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )

    application.include_router(auth_router)
    application.include_router(approval_router)
    application.include_router(job_router)
    application.include_router(memory_router)
    application.include_router(operations_router)
    application.include_router(task_router)
    application.include_router(routine_router)
    application.include_router(calendar_router)
    application.include_router(document_router)
    application.include_router(invoice_router)
    application.include_router(installation_router)
    application.include_router(finance_router)
    application.include_router(email_router)
    application.include_router(answer_router)
    application.include_router(reminder_router)
    application.include_router(notification_router)
    application.include_router(discovery_router)
    application.include_router(context_router)
    application.include_router(work_router)

    @application.exception_handler(RequestValidationError)
    async def sanitized_validation_error(request, exc):
        return JSONResponse({"detail": "Invalid request"}, status_code=422)

    @application.middleware("http")
    async def response_security(request, call_next):
        response = await call_next(request)
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Content-Security-Policy"] = "default-src 'none'; frame-ancestors 'none'"
        return response

    @application.get("/api/v1/live")
    def live() -> dict[str, str]:
        return {"status": "ok"}

    @application.get("/api/v1/health")
    def ready() -> JSONResponse:
        try:
            with SessionLocal() as session:
                session.execute(text("SELECT 1"))
        except SQLAlchemyError:
            # Do not disclose credentials, exception strings, topology or model configuration.
            return JSONResponse({"status": "unavailable"}, status_code=503)
        return JSONResponse({"status": "ok"})

    @application.get("/api/v1/system/summary", dependencies=[Depends(require_identity_foundation)])
    def system_summary() -> None:
        pass

    @application.get("/api/v1/speech/status", dependencies=[Depends(require_identity_foundation)])
    def speech_status() -> None:
        pass

    @application.post(
        "/api/v1/speech/synthesize", dependencies=[Depends(require_identity_foundation)]
    )
    def synthesize_speech() -> None:
        pass

    return application


app = create_app()
