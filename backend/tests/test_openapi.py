"""The OpenAPI schema is what the mobile client's types are generated from (Phase 3).

PUT replaces a whole resource, so a field left out must be an error, never a
silent "clear this". These tests keep every request field required in the
schema, including the ones that may be null: a generated client then types
them ``T | null`` rather than optional, and has to send null on purpose
(ADR 0010).
"""

from typing import Any

import pytest

from app.main import app

SCHEMAS: dict[str, Any] = app.openapi()["components"]["schemas"]

RESOURCE_REQUESTS = [
    "IncomeSourceRequest",
    "WeeklySchedule",
    "BiweeklySchedule",
    "SemiMonthlySchedule",
    "MonthlySchedule",
    "BillRequest",
    "EssentialExpenseRequest",
    "DebtRequest",
    "GoalRequest",
    "BalanceSnapshotRequest",
]


def test_every_resource_request_schema_is_checked_here() -> None:
    paths = app.openapi()["paths"]
    referenced = {
        operation["requestBody"]["content"]["application/json"]["schema"]["$ref"].split("/")[-1]
        for path, operations in paths.items()
        if not path.startswith("/auth")
        for operation in operations.values()
        if "requestBody" in operation
    }
    assert referenced <= set(RESOURCE_REQUESTS)
    assert len(referenced) == 6


@pytest.mark.parametrize("name", RESOURCE_REQUESTS)
def test_every_request_field_is_required_and_no_others_are_allowed(name: str) -> None:
    schema = SCHEMAS[name]
    assert set(schema["required"]) == set(schema["properties"])
    assert schema["additionalProperties"] is False


@pytest.mark.parametrize(
    ("name", "field"), [("BillRequest", "repeat_every_months"), ("GoalRequest", "deadline")]
)
def test_a_nullable_field_is_required_and_says_it_takes_null(name: str, field: str) -> None:
    schema = SCHEMAS[name]
    assert field in schema["required"]
    assert {"type": "null"} in schema["properties"][field]["anyOf"]
    assert "null" in schema["properties"][field]["description"]
