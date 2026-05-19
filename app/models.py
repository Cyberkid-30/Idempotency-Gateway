import hashlib
import json
from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import String, Integer, Text, DateTime, Enum
from sqlalchemy.orm import Mapped, mapped_column
import enum

from .database import Base


class RequestStatus(str, enum.Enum):
    IN_FLIGHT = "in_flight"
    COMPLETED = "completed"


class IdempotencyRecord(Base):
    __tablename__ = "idempotency_records"

    id: Mapped[str] = mapped_column(
        String(255), primary_key=True, index=True, default=lambda: str(uuid4())
    )
    idempotency_key: Mapped[str] = mapped_column(
        String(255), unique=True, index=True, nullable=False
    )
    request_body_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    response_body: Mapped[str | None] = mapped_column(Text, nullable=True)
    response_status_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[RequestStatus] = mapped_column(
        Enum(RequestStatus), default=RequestStatus.IN_FLIGHT, nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    @staticmethod
    def hash_body(body: dict) -> str:
        """Deterministically hash a request body dict."""
        canonical = json.dumps(body, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode()).hexdigest()
