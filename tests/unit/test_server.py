"""Offline checks of the HTTP server that Cloud Run runs."""

import pytest
from fastapi.testclient import TestClient


@pytest.fixture(scope="module")
def client():
    from app.main import app

    return TestClient(app)


def test_health(client):
    assert client.get("/health").json() == {"status": "ok"}


def test_lists_agent(client):
    assert client.get("/list-apps").json() == ["simpleagent"]


def test_creates_session(client):
    resp = client.post("/apps/simpleagent/users/test-user/sessions")
    assert resp.status_code == 200
    assert resp.json()["appName"] == "simpleagent"
