"""No user can see, change, or delete another user's data (ADR 0006, ADR 0010).

One test per verb, run for every resource in conftest.py's ``RESOURCES``:
``resource`` is each of them, ``item_resource`` each one that has GET by id, PUT,
and DELETE. Another user's row must answer exactly like a row that does not
exist: same status, same body.
"""

import uuid
from typing import Any

from fastapi.testclient import TestClient

type Json = dict[str, Any]
type Headers = dict[str, str]
type Resource = Any  # conftest.Resource


def create(client: TestClient, resource: Resource, headers: Headers) -> Json:
    response = client.post(resource.path, json=resource.body, headers=headers)
    assert response.status_code == 201, response.text
    return dict(response.json())


def listed(client: TestClient, resource: Resource, headers: Headers) -> list[Json]:
    response = client.get(resource.path, headers=headers)
    assert response.status_code == 200, response.text
    return list(response.json()["items"])


def assert_same_as_missing(response: Any, missing: Any) -> None:
    """``response`` (for another user's row) must match ``missing`` (for no row at all)."""
    assert response.status_code == missing.status_code == 404, response.text
    assert response.json() == missing.json()
    assert response.json()["error"]["code"] == "not_found"


def test_list_never_includes_another_users_rows(
    client: TestClient, resource: Resource, ada: Headers, bob: Headers
) -> None:
    adas = create(client, resource, ada)
    assert listed(client, resource, bob) == []

    bobs = create(client, resource, bob)
    assert listed(client, resource, bob) == [bobs]
    assert listed(client, resource, ada) == [adas]


def test_create_cannot_name_another_owner(
    client: TestClient, resource: Resource, ada: Headers, bob: Headers
) -> None:
    ada_id = client.get("/me", headers=ada).json()["id"]

    response = client.post(resource.path, json={**resource.body, "user_id": ada_id}, headers=bob)

    assert response.status_code == 422, response.text
    assert "user_id" in response.json()["error"]["message"]
    assert listed(client, resource, ada) == []
    assert listed(client, resource, bob) == []


def test_get_of_another_users_row_is_not_found(
    client: TestClient, item_resource: Resource, ada: Headers, bob: Headers
) -> None:
    path = item_resource.path
    adas = create(client, item_resource, ada)

    response = client.get(f"{path}/{adas['id']}", headers=bob)

    assert_same_as_missing(response, client.get(f"{path}/{uuid.uuid4()}", headers=bob))
    assert client.get(f"{path}/{adas['id']}", headers=ada).json() == adas


def test_put_to_another_users_row_is_not_found_and_changes_nothing(
    client: TestClient, item_resource: Resource, ada: Headers, bob: Headers
) -> None:
    path, replacement = item_resource.path, item_resource.replacement
    adas = create(client, item_resource, ada)

    response = client.put(f"{path}/{adas['id']}", json=replacement, headers=bob)

    missing = client.put(f"{path}/{uuid.uuid4()}", json=replacement, headers=bob)
    assert_same_as_missing(response, missing)
    assert client.get(f"{path}/{adas['id']}", headers=ada).json() == adas
    assert listed(client, item_resource, bob) == []


def test_delete_of_another_users_row_is_not_found_and_deletes_nothing(
    client: TestClient, item_resource: Resource, ada: Headers, bob: Headers
) -> None:
    path = item_resource.path
    adas = create(client, item_resource, ada)

    response = client.delete(f"{path}/{adas['id']}", headers=bob)

    assert_same_as_missing(response, client.delete(f"{path}/{uuid.uuid4()}", headers=bob))
    assert client.get(f"{path}/{adas['id']}", headers=ada).json() == adas
