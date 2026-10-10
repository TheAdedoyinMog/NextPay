"""What every resource API has in common, run for each one (ADR 0010).

``resource`` is each entry of conftest.py's ``RESOURCES``; ``item_resource`` is
each one that has GET by id, PUT, and DELETE. Rules that belong to one resource
are in that resource's own test file.
"""

import uuid
from typing import Any

import pytest
from fastapi.testclient import TestClient

type Json = dict[str, Any]
type Headers = dict[str, str]
type Resource = Any  # conftest.Resource


def create(client: TestClient, resource: Resource, headers: Headers) -> Json:
    response = client.post(resource.path, json=resource.body, headers=headers)
    assert response.status_code == 201, response.text
    return dict(response.json())


def assert_error(response: Any, status: int, code: str) -> Json:
    assert response.status_code == status, response.text
    body = response.json()
    assert set(body) == {"error"} and body["error"]["code"] == code
    return dict(body["error"])


# --- every resource: create and list -------------------------------------------


def test_a_new_user_has_none(client: TestClient, resource: Resource, ada: Headers) -> None:
    response = client.get(resource.path, headers=ada)
    assert response.status_code == 200
    assert response.json() == {"items": []}


def test_create_returns_what_was_sent_and_lists_it(
    client: TestClient, resource: Resource, ada: Headers
) -> None:
    created = create(client, resource, ada)

    uuid.UUID(created["id"])
    assert {"id", "created_at", *resource.body} <= set(created)
    assert {name: created[name] for name in resource.body} == resource.body
    assert "user_id" not in created
    assert client.get(resource.path, headers=ada).json() == {"items": [created]}


def test_create_requires_every_field(client: TestClient, resource: Resource, ada: Headers) -> None:
    for field in resource.body:
        body = {name: value for name, value in resource.body.items() if name != field}
        error = assert_error(
            client.post(resource.path, json=body, headers=ada), 422, "validation_error"
        )
        assert field in error["message"]
    assert client.get(resource.path, headers=ada).json() == {"items": []}


def test_create_rejects_unknown_fields(
    client: TestClient, resource: Resource, ada: Headers
) -> None:
    response = client.post(resource.path, json={**resource.body, "surprise": 1}, headers=ada)
    assert "surprise" in assert_error(response, 422, "validation_error")["message"]


@pytest.mark.parametrize("method", ["POST", "GET"])
def test_the_collection_requires_a_signed_in_user(
    client: TestClient, resource: Resource, ada: Headers, method: str
) -> None:
    body = resource.body if method == "POST" else None

    response = client.request(method, resource.path, json=body)

    assert_error(response, 401, "not_authenticated")
    assert response.headers["www-authenticate"] == "Bearer"
    assert client.get(resource.path, headers=ada).json() == {"items": []}


# --- resources with item routes: get, replace, delete --------------------------


def test_get_returns_the_item(client: TestClient, item_resource: Resource, ada: Headers) -> None:
    created = create(client, item_resource, ada)
    response = client.get(f"{item_resource.path}/{created['id']}", headers=ada)
    assert response.status_code == 200
    assert response.json() == created


def test_put_replaces_every_field_and_keeps_the_id(
    client: TestClient, item_resource: Resource, ada: Headers
) -> None:
    path, replacement = item_resource.path, item_resource.replacement
    created = create(client, item_resource, ada)

    response = client.put(f"{path}/{created['id']}", json=replacement, headers=ada)

    assert response.status_code == 200, response.text
    updated = response.json()
    assert updated == {**created, **replacement, "updated_at": updated["updated_at"]}
    assert client.get(f"{path}/{created['id']}", headers=ada).json() == updated
    assert client.get(path, headers=ada).json() == {"items": [updated]}


def test_put_needs_the_whole_item(
    client: TestClient, item_resource: Resource, ada: Headers
) -> None:
    path = item_resource.path
    created = create(client, item_resource, ada)
    for field in item_resource.replacement:
        partial = {name: v for name, v in item_resource.replacement.items() if name != field}
        response = client.put(f"{path}/{created['id']}", json=partial, headers=ada)
        assert field in assert_error(response, 422, "validation_error")["message"]
    assert client.get(f"{path}/{created['id']}", headers=ada).json() == created


def test_delete_removes_only_that_item(
    client: TestClient, item_resource: Resource, ada: Headers
) -> None:
    path = item_resource.path
    created = create(client, item_resource, ada)
    other = client.post(path, json=item_resource.replacement, headers=ada).json()

    response = client.delete(f"{path}/{created['id']}", headers=ada)

    assert response.status_code == 204
    assert response.content == b""
    assert_error(client.get(f"{path}/{created['id']}", headers=ada), 404, "not_found")
    assert_error(client.delete(f"{path}/{created['id']}", headers=ada), 404, "not_found")
    assert client.get(path, headers=ada).json() == {"items": [other]}


@pytest.mark.parametrize("method", ["GET", "PUT", "DELETE"])
def test_an_unknown_id_is_not_found(
    client: TestClient, item_resource: Resource, ada: Headers, method: str
) -> None:
    create(client, item_resource, ada)
    body = item_resource.replacement if method == "PUT" else None
    response = client.request(
        method, f"{item_resource.path}/{uuid.uuid4()}", json=body, headers=ada
    )
    assert assert_error(response, 404, "not_found") == {
        "code": "not_found",
        "message": "Not found.",
    }


@pytest.mark.parametrize("method", ["GET", "PUT", "DELETE"])
def test_a_malformed_id_is_a_validation_error(
    client: TestClient, item_resource: Resource, ada: Headers, method: str
) -> None:
    body = item_resource.replacement if method == "PUT" else None
    response = client.request(method, f"{item_resource.path}/not-a-uuid", json=body, headers=ada)
    assert "_id" in assert_error(response, 422, "validation_error")["message"]


@pytest.mark.parametrize("method", ["GET", "PUT", "DELETE"])
def test_an_item_requires_a_signed_in_user(
    client: TestClient, item_resource: Resource, ada: Headers, method: str
) -> None:
    path = item_resource.path
    created = create(client, item_resource, ada)
    body = item_resource.replacement if method == "PUT" else None

    response = client.request(method, f"{path}/{created['id']}", json=body)

    assert_error(response, 401, "not_authenticated")
    assert response.headers["www-authenticate"] == "Bearer"
    assert client.get(f"{path}/{created['id']}", headers=ada).json() == created
