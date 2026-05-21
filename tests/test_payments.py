"""
Tests for the Idempotency Gateway.

Run with:
    pytest tests/ -v

"""

import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base, get_db
from app.main import app

TEST_DATABASE_URL = "sqlite:///./test.db"
engine = create_engine(TEST_DATABASE_URL)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


app.dependency_overrides[get_db] = override_get_db


@pytest.fixture(autouse=True)
def setup_db():
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


client = TestClient(app)

ENDPOINT = "/api/v1/process-payment"
HEADERS_BASE = {"Content-Type": "application/json"}


def make_key() -> str:
    return str(uuid.uuid4())


# ---------------------------------------------------------------------------
# User Story 1: Happy Path
# ---------------------------------------------------------------------------


def test_first_payment_returns_201():
    key = make_key()
    resp = client.post(
        ENDPOINT,
        json={"amount": 100, "currency": "GHS"},
        headers={**HEADERS_BASE, "Idempotency-Key": key},
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["message"] == "Charged 100.0 GHS"
    assert body["idempotency_key"] == key
    assert "X-Cache-Hit" not in resp.headers


def test_health_check():
    resp = client.get("/api/v1/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_missing_idempotency_key_returns_422():
    resp = client.post(ENDPOINT, json={"amount": 50, "currency": "GHS"})
    assert resp.status_code == 422


def test_invalid_amount_rejected():
    key = make_key()
    resp = client.post(
        ENDPOINT,
        json={"amount": -10, "currency": "GHS"},
        headers={**HEADERS_BASE, "Idempotency-Key": key},
    )
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# User Story 2: Idempotency — Duplicate Request
# ---------------------------------------------------------------------------


def test_duplicate_request_returns_cached_response():
    key = make_key()
    payload = {"amount": 250, "currency": "USD"}

    resp1 = client.post(
        ENDPOINT, json=payload, headers={**HEADERS_BASE, "Idempotency-Key": key}
    )
    assert resp1.status_code == 201

    resp2 = client.post(
        ENDPOINT, json=payload, headers={**HEADERS_BASE, "Idempotency-Key": key}
    )
    assert resp2.status_code == 201
    assert resp2.headers.get("X-Cache-Hit") == "true"
    assert resp2.json() == resp1.json()


def test_duplicate_does_not_reprocess():
    """The duplicate must be instant (no 2-second delay)."""
    import time

    key = make_key()
    payload = {"amount": 75, "currency": "EUR"}

    client.post(
        ENDPOINT, json=payload, headers={**HEADERS_BASE, "Idempotency-Key": key}
    )

    start = time.time()
    resp = client.post(
        ENDPOINT, json=payload, headers={**HEADERS_BASE, "Idempotency-Key": key}
    )
    elapsed = time.time() - start

    assert resp.headers.get("X-Cache-Hit") == "true"
    assert elapsed < 1.0, f"Duplicate request took too long: {elapsed:.2f}s"


# ---------------------------------------------------------------------------
# User Story 3: Different Body, Same Key → Conflict
# ---------------------------------------------------------------------------


def test_same_key_different_body_returns_409():
    key = make_key()

    resp1 = client.post(
        ENDPOINT,
        json={"amount": 100, "currency": "GHS"},
        headers={**HEADERS_BASE, "Idempotency-Key": key},
    )
    assert resp1.status_code == 201

    resp2 = client.post(
        ENDPOINT,
        json={"amount": 500, "currency": "GHS"},
        headers={**HEADERS_BASE, "Idempotency-Key": key},
    )
    assert resp2.status_code == 409
    assert "different request body" in resp2.json()["detail"].lower()


# ---------------------------------------------------------------------------
# Developer's Choice: Currency validation
# ---------------------------------------------------------------------------


def test_currency_normalized_to_uppercase():
    key = make_key()
    resp = client.post(
        ENDPOINT,
        json={"amount": 30, "currency": "ghs"},
        headers={**HEADERS_BASE, "Idempotency-Key": key},
    )
    assert resp.status_code == 201
    assert resp.json()["currency"] == "GHS"


def test_invalid_currency_length_rejected():
    key = make_key()
    resp = client.post(
        ENDPOINT,
        json={"amount": 30, "currency": "GHSXX"},
        headers={**HEADERS_BASE, "Idempotency-Key": key},
    )
    assert resp.status_code == 422
