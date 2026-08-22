"""API-boundary tests for server-verified identity and the embedding-surface headers.

The API never accepts a client-supplied ``actor``: the verified Principal resolved by the
active IdentityPort supplies the audit actor. Under the local profile that is a seeded dev
persona (default = the first persona; selected via ``X-Dev-Persona``); an unknown persona
is a 401. The CSP ``frame-ancestors`` middleware guards who may iframe the planner.
"""

from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient
from tests.conftest import LOOPBACK_PEER

from campaign_planner.api import deps
from campaign_planner.api.app import app
from campaign_planner.config import Container

_PLAN_BODY: dict[str, Any] = {
    "objective": "savings account acquisition",
    "market": "SG",
    "vertical": "banking",
    "total_budget": 120000,
    "start_date": "2026-07-01",
    "end_date": "2026-07-28",
}


@pytest.fixture
def client(local_container: Container, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    """A TestClient whose routes resolve the in-memory local container."""
    monkeypatch.setattr(deps, "get_container", lambda: local_container)
    return TestClient(app, client=LOOPBACK_PEER)


def test_healthz_exposes_profile(client: TestClient) -> None:
    body = client.get("/healthz").json()
    assert body["status"] == "ok"
    assert body["profile"] == "local"  # the UI persona picker gates on this


def test_personas_listed_under_local_profile(client: TestClient) -> None:
    personas = client.get("/v1/personas").json()
    ids = {p["id"] for p in personas}
    assert {"analyst", "approver", "auditor", "other-tenant"} <= ids


def test_unknown_dev_persona_is_401(client: TestClient) -> None:
    response = client.post("/v1/plan", json=_PLAN_BODY, headers={"X-Dev-Persona": "does-not-exist"})
    assert response.status_code == 401
    assert response.json()["detail"] == "authentication required"


def test_default_persona_becomes_audit_actor(
    client: TestClient, local_container: Container
) -> None:
    response = client.post("/v1/plan", json=_PLAN_BODY)
    assert response.status_code == 200
    assert response.json()["requires_human_review"] is True
    recorded = local_container.audit.read_all()
    assert recorded, "the plan build must write an audit record"
    assert recorded[-1]["actor"] == "demo.analyst@bank.example"


def test_selected_persona_becomes_audit_actor(
    client: TestClient, local_container: Container
) -> None:
    response = client.post("/v1/plan", json=_PLAN_BODY, headers={"X-Dev-Persona": "auditor"})
    assert response.status_code == 200
    recorded = local_container.audit.read_all()
    assert recorded[-1]["actor"] == "demo.auditor@bank.example"


def test_embedding_surface_headers_present(client: TestClient) -> None:
    response = client.get("/healthz")
    assert "frame-ancestors" in response.headers.get("content-security-policy", "")
    # Default allowlist is 'self', so the legacy header is emitted too.
    if "'self'" in response.headers["content-security-policy"]:
        assert response.headers.get("x-frame-options") == "SAMEORIGIN"
