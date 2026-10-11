"""PUT /me/settings: the signed-in user's time zone and goal share."""

from typing import Any

import pytest
from fastapi.testclient import TestClient

type Json = dict[str, Any]
type Headers = dict[str, str]

SETTINGS: Json = {"timezone": "America/New_York", "no_deadline_goal_share_bps": 3500}


def assert_error(response: Any, status: int, code: str) -> Json:
    assert response.status_code == status, response.text
    body = response.json()
    assert set(body) == {"error"} and body["error"]["code"] == code
    return dict(body["error"])


def test_a_new_user_plans_in_utc_with_a_20_percent_share(client: TestClient, ada: Headers) -> None:
    me = client.get("/me", headers=ada).json()
    assert (me["timezone"], me["no_deadline_goal_share_bps"]) == ("UTC", 2000)


def test_put_replaces_the_settings(client: TestClient, ada: Headers, bob: Headers) -> None:
    before = client.get("/me", headers=ada).json()

    response = client.put("/me/settings", json=SETTINGS, headers=ada)

    assert response.status_code == 200, response.text
    assert response.json() == {**before, **SETTINGS}
    assert client.get("/me", headers=ada).json() == {**before, **SETTINGS}
    # Only this user's.
    assert client.get("/me", headers=bob).json()["timezone"] == "UTC"


@pytest.mark.parametrize(
    ("change", "code", "mention"),
    [
        ({"timezone": "Mars/Olympus_Mons"}, "invalid_input", "time zone"),
        ({"timezone": ""}, "validation_error", "timezone"),
        ({"timezone": "x" * 65}, "validation_error", "timezone"),
        ({"timezone": None}, "validation_error", "timezone"),
        ({"no_deadline_goal_share_bps": -1}, "validation_error", "no_deadline_goal_share_bps"),
        ({"no_deadline_goal_share_bps": 10_001}, "validation_error", "no_deadline_goal_share_bps"),
        ({"no_deadline_goal_share_bps": 20.5}, "validation_error", "no_deadline_goal_share_bps"),
        ({"email": "new@example.com"}, "validation_error", "email"),
    ],
)
def test_invalid_settings_are_rejected_and_change_nothing(
    client: TestClient, ada: Headers, change: Json, code: str, mention: str
) -> None:
    before = client.get("/me", headers=ada).json()
    response = client.put("/me/settings", json={**SETTINGS, **change}, headers=ada)
    assert mention in assert_error(response, 422, code)["message"]
    assert client.get("/me", headers=ada).json() == before


@pytest.mark.parametrize("field", sorted(SETTINGS))
def test_put_needs_every_setting(client: TestClient, ada: Headers, field: str) -> None:
    body = {name: value for name, value in SETTINGS.items() if name != field}
    response = client.put("/me/settings", json=body, headers=ada)
    assert field in assert_error(response, 422, "validation_error")["message"]


def test_settings_require_a_signed_in_user(client: TestClient) -> None:
    assert_error(client.put("/me/settings", json=SETTINGS), 401, "not_authenticated")
