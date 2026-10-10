"""Central error handling: every error leaves the API in one envelope."""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import BaseModel

from app.api.errors import install_error_handlers
from app.core.errors import DomainError, EmailUnavailableError, InvalidInputError
from app.main import app


class _UnmappedError(DomainError):
    code = "unmapped"
    message = "No status was chosen for this."


class _Body(BaseModel):
    name: str


@pytest.fixture
def client() -> TestClient:
    test_app = FastAPI()
    install_error_handlers(test_app)

    @test_app.get("/raise/{kind}")
    def raise_(kind: str) -> None:
        errors: dict[str, DomainError] = {
            "unmapped": _UnmappedError(),
            "invalid": InvalidInputError("Pick a shorter name."),
            "taken": EmailUnavailableError(),
        }
        raise errors[kind]

    @test_app.post("/echo")
    def echo(body: _Body) -> _Body:
        return body

    return TestClient(test_app)


@pytest.mark.parametrize(
    ("kind", "status", "code", "message"),
    [
        ("invalid", 422, "invalid_input", "Pick a shorter name."),
        ("taken", 409, "email_unavailable", "This email can't be used to create an account."),
        ("unmapped", 400, "unmapped", "No status was chosen for this."),
    ],
)
def test_domain_errors_map_to_their_status(
    client: TestClient, kind: str, status: int, code: str, message: str
) -> None:
    response = client.get(f"/raise/{kind}")
    assert response.status_code == status
    assert response.json() == {"error": {"code": code, "message": message}}
    assert "www-authenticate" not in response.headers


def test_a_missing_body_is_a_validation_error(client: TestClient) -> None:
    response = client.post("/echo")
    assert response.status_code == 422
    assert response.json()["error"] == {
        "code": "validation_error",
        "message": "Check these fields: body",
    }


def test_unknown_routes_and_methods_use_the_envelope() -> None:
    client = TestClient(app)
    assert client.get("/nowhere").json() == {"error": {"code": "not_found", "message": "Not Found"}}
    wrong_method = client.delete("/health")
    assert wrong_method.status_code == 405
    assert wrong_method.json()["error"]["code"] == "method_not_allowed"
    assert wrong_method.headers["allow"] == "GET"
