from contextlib import contextmanager
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError

from app.main import app


@pytest.fixture
def client():
    with TestClient(app) as client:
        yield client


def test_live_has_no_dependencies(client):
    with patch("app.main.SessionLocal", side_effect=AssertionError("database queried")):
        response = client.get("/api/v1/live")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_ready_does_not_call_inference(client):
    @contextmanager
    def healthy_database():
        class Session:
            def execute(self, statement):
                assert str(statement) == "SELECT 1"

        yield Session()

    with patch("app.main.SessionLocal", healthy_database):
        response = client.get("/api/v1/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_database_failure_is_unready_without_leaking_details(client):
    secret = "postgresql://private:credential@private-nas"
    with patch(
        "app.main.SessionLocal", side_effect=OperationalError(secret, {}, Exception(secret))
    ):
        response = client.get("/api/v1/health")
    assert response.status_code == 503
    assert response.json() == {"status": "unavailable"}
    assert secret not in response.text


@pytest.mark.parametrize(
    "method,path",
    [
        ("GET", "/api/v1/system/summary"),
        ("GET", "/api/v1/speech/status"),
        ("POST", "/api/v1/speech/synthesize"),
    ],
)
@pytest.mark.parametrize("headers", [{}, {"Authorization": "Bearer invented", "X-User": "admin"}])
def test_unfinished_capabilities_fail_closed(client, method, path, headers):
    with patch("app.main.SessionLocal", side_effect=AssertionError("database accessed")):
        response = client.request(method, path, headers=headers)
    assert response.status_code == 503
    assert response.json() == {"detail": "Identity foundation is not enabled"}


@pytest.mark.parametrize("path", ["/docs", "/redoc", "/openapi.json"])
def test_public_schema_is_disabled(client, path):
    assert client.get(path).status_code == 404


def test_security_headers_also_cover_denials(client):
    response = client.get("/api/v1/system/summary")
    assert response.headers["Cache-Control"] == "no-store"
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert "frame-ancestors 'none'" in response.headers["Content-Security-Policy"]
