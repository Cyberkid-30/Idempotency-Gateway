import json
import threading
import time
from datetime import datetime, timezone
from typing import Tuple

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .models import IdempotencyRecord, RequestStatus
from .schemas import PaymentRequest

# In-process lock registry for in-flight requests to handle concurrent requests with the same key.
# Maps idempotency_key -> threading.Event
_in_flight_events: dict[str, threading.Event] = {}
_in_flight_lock = threading.Lock()


class ConflictError(Exception):
    """Raised when the same key is reused with a different request body."""

    pass


class IdempotencyService:
    def get_or_create_record(
        self,
        db: Session,
        idempotency_key: str,
        body_hash: str,
    ) -> Tuple[IdempotencyRecord | None, bool]:
        """
        Try to fetch an existing record for this key.
        Returns (record_or_none, is_new).
        If the key exists with a different body_hash, raises ConflictError.
        """
        existing = (
            db.query(IdempotencyRecord)
            .filter(IdempotencyRecord.idempotency_key == idempotency_key)
            .first()
        )

        if existing:
            if existing.request_body_hash != body_hash:
                raise ConflictError(
                    "Idempotency key already used for a different request body."
                )
            return existing, False

        # Create a new IN_FLIGHT record — use INSERT to race-safely detect duplicates
        record = IdempotencyRecord(
            idempotency_key=idempotency_key,
            request_body_hash=body_hash,
            status=RequestStatus.IN_FLIGHT,
        )
        try:
            db.add(record)
            db.commit()
            db.refresh(record)
            return record, True
        except IntegrityError:
            db.rollback()
            # Another request won the race and inserted first — fetch it
            existing = (
                db.query(IdempotencyRecord)
                .filter(IdempotencyRecord.idempotency_key == idempotency_key)
                .first()
            )
            if existing and existing.request_body_hash != body_hash:
                raise ConflictError(
                    "Idempotency key already used for a different request body."
                )
            return existing, False

    def complete_record(
        self,
        db: Session,
        record: IdempotencyRecord,
        response_body: dict,
        status_code: int,
    ) -> None:
        record.response_body = json.dumps(response_body)
        record.response_status_code = status_code
        record.status = RequestStatus.COMPLETED
        record.completed_at = datetime.now(timezone.utc)
        db.commit()

    def process_payment(
        self,
        db: Session,
        idempotency_key: str,
        payment: PaymentRequest,
    ) -> Tuple[dict, int, bool]:
        """
        Main entry point.
        Returns (response_body, status_code, cache_hit).
        Handles in-flight deduplication via threading.Event.
        """
        body_hash = IdempotencyRecord.hash_body(payment.model_dump())

        # --- In-flight check (bonus race-condition guard) ---
        with _in_flight_lock:
            if idempotency_key in _in_flight_events:
                # Another thread is currently processing this key — wait for it
                event = _in_flight_events[idempotency_key]
            else:
                event = None

        if event is not None:
            # Block until the first request finishes (max 30s)
            event.wait(timeout=30)
            # Now the DB record should be COMPLETED — fetch and replay
            existing = (
                db.query(IdempotencyRecord)
                .filter(IdempotencyRecord.idempotency_key == idempotency_key)
                .first()
            )
            if existing and existing.status == RequestStatus.COMPLETED:
                return (
                    json.loads(existing.response_body),  # type: ignore
                    existing.response_status_code,  # type: ignore
                    True,
                )
            # Fallback: something went wrong with the primary request, treat as new
        # --- End in-flight check ---

        record, is_new = self.get_or_create_record(db, idempotency_key, body_hash)

        if not is_new:
            # Existing COMPLETED record — replay cached response
            if record.status == RequestStatus.COMPLETED:  # type: ignore
                return (
                    json.loads(record.response_body),  # type: ignore
                    record.response_status_code,  # type: ignore
                    True,
                )

            # Record is IN_FLIGHT (persisted but no in-memory event — e.g. server restart)
            # Wait briefly and re-query
            time.sleep(2)
            db.refresh(record)
            if record.status == RequestStatus.COMPLETED:  # type: ignore
                return (
                    json.loads(record.response_body),  # type: ignore
                    record.response_status_code,  # type: ignore
                    True,
                )

            # Still in-flight after wait — process anyway as safety net

        # --- This is a NEW request: register in-flight event ---
        my_event = threading.Event()
        with _in_flight_lock:
            _in_flight_events[idempotency_key] = my_event

        try:
            # Simulate payment processing (2-second delay)
            time.sleep(2)

            response_body = {
                "status": "success",
                "message": f"Charged {payment.amount} {payment.currency}",
                "idempotency_key": idempotency_key,
                "amount": payment.amount,
                "currency": payment.currency,
            }
            status_code = 201

            self.complete_record(db, record, response_body, status_code)  # type: ignore
            return response_body, status_code, False

        finally:
            # Signal any waiting threads and clean up
            with _in_flight_lock:
                _in_flight_events.pop(idempotency_key, None)
            my_event.set()


idempotency_service = IdempotencyService()
