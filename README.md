# Idempotency Gateway — Pay-Once Protocol

A production-grade payment processing API that guarantees **exactly-once execution**, built for FinSafe Transactions Ltd. No matter how many times a client retries a request, the payment is processed only once.

---

## Architecture Diagram

### Sequence Diagram

```
Client                  API Gateway                  PostgreSQL
  |                          |                             |
  |-- POST /process-payment ->|                             |
  |   Idempotency-Key: K1    |                             |
  |   { amount: 100 }        |                             |
  |                          |-- SELECT WHERE key=K1 ----->|
  |                          |<-- (no record found) -------|
  |                          |                             |
  |                          |-- INSERT key=K1,            |
  |                          |   status=IN_FLIGHT -------->|
  |                          |                             |
  |                          |   [simulate 2s processing]  |
  |                          |                             |
  |                          |-- UPDATE status=COMPLETED ->|
  |                          |   response_body stored      |
  |<-- 201 Created ----------|                             |
  |   { "Charged 100 GHS" }  |                             |
  |                          |                             |
  |                          |                             |
  |-- POST /process-payment ->|  (retry / duplicate)       |
  |   Idempotency-Key: K1    |                             |
  |   { amount: 100 }        |                             |
  |                          |-- SELECT WHERE key=K1 ----->|
  |                          |<-- (COMPLETED record found) |
  |<-- 201 Created ----------|                             |
  |   X-Cache-Hit: true      |                             |
  |   { "Charged 100 GHS" }  |                             |
  |                          |                             |
  |                          |                             |
  |-- POST /process-payment ->|  (fraud attempt)           |
  |   Idempotency-Key: K1    |                             |
  |   { amount: 500 }        |                             |
  |                          |-- SELECT WHERE key=K1 ----->|
  |                          |<-- (hash mismatch!) --------|
  |<-- 409 Conflict ---------|                             |
  |   "Key used for          |                             |
  |    different body"       |                             |
```

---

## Setup Instructions

### Prerequisites

- Python 3.11+
- PostgreSQL 14+ running locally (or via Docker)

### 1. Clone the repository

```bash
git clone https://github.com/Cyberkid-30/Idempotency-Gateway.git
cd Idempotency-Gateway
```

### 2. Create and activate a virtual environment

```bash
python -m venv venv
source venv/bin/activate       # Linux/macOS
venv\Scripts\activate          # Windows
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. Configure environment variables

```bash
touch .env
```

Edit `.env`:

```env
DATABASE_URL=postgresql://postgres:yourpassword@localhost:5432/idempotency_db
```

### 5. Create the database

```bash
# In psql or your PostgreSQL client:
CREATE DATABASE idempotency_db;
```

Tables are created automatically on server startup via SQLAlchemy's `create_all`.

### 6. Start the server

```bash
python main.py
# or
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

The API is now live at `http://localhost:8000`.  
Interactive docs: `http://localhost:8000/docs`

---

## Running Tests

Tests use SQLite in-memory (no PostgreSQL required):

```bash
pytest tests/ -v
```

Expected output:

```
tests/test_payments.py::test_first_payment_returns_201 PASSED
tests/test_payments.py::test_health_check PASSED
tests/test_payments.py::test_missing_idempotency_key_returns_422 PASSED
tests/test_payments.py::test_invalid_amount_rejected PASSED
tests/test_payments.py::test_duplicate_request_returns_cached_response PASSED
tests/test_payments.py::test_duplicate_does_not_reprocess PASSED
tests/test_payments.py::test_same_key_different_body_returns_409 PASSED
tests/test_payments.py::test_currency_normalized_to_uppercase PASSED
tests/test_payments.py::test_invalid_currency_length_rejected PASSED

9 passed in ~12s
```

---

## API Documentation

### Base URL

```
http://localhost:8000/api/v1
```

---

### `POST /process-payment`

Process a payment. The request is idempotent — retrying with the same `Idempotency-Key` and body returns the cached response immediately.

#### Request Headers

| Header            | Required | Description                                        |
| ----------------- | -------- | -------------------------------------------------- |
| `Idempotency-Key` | ✅ Yes   | A unique string (UUID recommended) per transaction |
| `Content-Type`    | ✅ Yes   | `application/json`                                 |

#### Request Body

```json
{
  "amount": 100.0,
  "currency": "GHS"
}
```

| Field      | Type   | Constraints                                                                            |
| ---------- | ------ | -------------------------------------------------------------------------------------- |
| `amount`   | float  | Required, must be > 0                                                                  |
| `currency` | string | Required, exactly 3 characters (ISO 4217). Case-insensitive — normalized to uppercase. |

#### Responses

**`201 Created` — First request, payment processed**

```json
{
  "status": "success",
  "message": "Charged 100.0 GHS",
  "idempotency_key": "a1b2c3d4-...",
  "amount": 100.0,
  "currency": "GHS"
}
```

**`201 Created` — Duplicate request (cached replay)**

Same body as above, plus:

```
X-Cache-Hit: true
```

**`409 Conflict` — Same key, different body**

```json
{
  "detail": "Idempotency key already used for a different request body."
}
```

**`422 Unprocessable Entity` — Validation failure**

```json
{
  "detail": [
    {
      "loc": ["body", "amount"],
      "msg": "Input should be greater than 0",
      "type": "greater_than"
    }
  ]
}
```

---

### `GET /health`

Health check endpoint.

**`200 OK`**

```json
{
  "status": "ok",
  "service": "Idempotency Gateway"
}
```

---

### Example: cURL

**First request (processed):**

```bash
curl -X POST http://localhost:8000/api/v1/process-payment \
  -H "Content-Type: application/json" \
  -H "Idempotency-Key: 550e8400-e29b-41d4-a716-446655440000" \
  -d '{"amount": 100, "currency": "GHS"}'
```

**Duplicate (instant cached response):**

```bash
curl -X POST http://localhost:8000/api/v1/process-payment \
  -H "Content-Type: application/json" \
  -H "Idempotency-Key: 550e8400-e29b-41d4-a716-446655440000" \
  -d '{"amount": 100, "currency": "GHS"}'
# Response header includes: X-Cache-Hit: true
```

**Fraud attempt (different body, same key):**

```bash
curl -X POST http://localhost:8000/api/v1/process-payment \
  -H "Content-Type: application/json" \
  -H "Idempotency-Key: 550e8400-e29b-41d4-a716-446655440000" \
  -d '{"amount": 500, "currency": "GHS"}'
# → 409 Conflict
```

---

## Design Decisions

### 1. PostgreSQL + SQLAlchemy ORM

PostgreSQL was chosen because its `UNIQUE` constraint on `idempotency_key` provides a database-level guarantee against duplicate inserts. Combined with catching `IntegrityError` on a racing insert, this handles concurrent requests from multiple server instances correctly — something an in-memory `dict` alone cannot provide.

### 2. Two-Phase Record Lifecycle: `IN_FLIGHT` → `COMPLETED`

Each record is inserted as `IN_FLIGHT` before processing begins, and updated to `COMPLETED` when the response is ready. This allows the system to detect concurrent requests to the _same key_ even before the first one finishes (the bonus race-condition scenario).

### 3. In-Process `threading.Event` for Race Conditions (Bonus)

For two requests hitting the **same server instance** simultaneously, a process-level `dict` of `threading.Event` objects allows Request B to _wait_ for Request A to complete rather than erroring out. Once Request A finishes and sets the event, Request B wakes up, reads the now-COMPLETED record from the database, and returns the same response. No double-processing, no 409 error — just a seamless wait-and-replay.

### 4. Deterministic Body Hashing

The request body is hashed using SHA-256 on its **canonical JSON form** (keys sorted, no whitespace). This ensures `{"amount":100,"currency":"GHS"}` and `{"currency":"GHS","amount":100}` are treated as identical, preventing spurious 409 errors due to key ordering differences.

---

## Developer's Choice: ISO 4217 Currency Validation

**Feature:** The `currency` field is validated to be exactly 3 characters and is automatically normalized to uppercase. Requests with currencies like `"ghsxx"` or `"X"` are rejected at the Pydantic layer with a 422 error before any database interaction.

**Why:** In a real Fintech system, accepting malformed currency codes would be dangerous — they could slip through to downstream ledger or settlement systems that expect strict ISO 4217 compliance (e.g. GHS, USD, EUR). Catching this at the API boundary is cheaper and safer than discovering corrupted currency data in reconciliation. The auto-uppercase normalization (`"ghs"` → `"GHS"`) also prevents case-sensitivity mismatches from triggering false 409 Conflict errors between clients.

---

## Project Structure

```
idempotency-gateway/
├── app/
│   ├── __init__.py
│   ├── config.py        # Pydantic settings (reads .env)
│   ├── database.py      # SQLAlchemy engine + session
│   ├── main.py          # FastAPI app, lifespan, middleware
│   ├── models.py        # IdempotencyRecord ORM model
│   ├── routes.py        # API endpoints
│   ├── schemas.py       # Pydantic request/response models
│   └── services.py      # Core idempotency + race-condition logic
├── tests/
│   └── test_payments.py # Pytest test suite (9 tests)
├── .env.example
├── alembic.ini
├── main.py              # Entry point (uvicorn)
├── requirements.txt
└── README.md
```
