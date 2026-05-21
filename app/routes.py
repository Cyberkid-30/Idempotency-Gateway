from fastapi import APIRouter, Depends, Header, HTTPException, Response
from sqlalchemy.orm import Session

from .database import get_db
from .schemas import ErrorResponse, PaymentRequest, PaymentResponse
from .services import ConflictError, idempotency_service

router = APIRouter()


@router.post(
    "/process-payment",
    status_code=201,
    responses={
        201: {
            "model": PaymentResponse,
            "description": "Payment processed successfully",
        },
        200: {
            "model": PaymentResponse,
            "description": "Duplicate request — cached response returned",
        },
        409: {
            "model": ErrorResponse,
            "description": "Key reused with different payload",
        },
        422: {"model": ErrorResponse, "description": "Validation error"},
    },
    summary="Process a payment (idempotent)",
    description=(
        "Submit a payment request. Include a unique `Idempotency-Key` header. "
        "Repeating the same key+body returns the original response without re-processing. "
        "Repeating the same key with a *different* body is rejected."
    ),
)
def process_payment(
    payment: PaymentRequest,
    response: Response,
    idempotency_key: str = Header(
        ...,
        alias="Idempotency-Key",
        description="A unique client-generated UUID or string per transaction attempt.",
    ),
    db: Session = Depends(get_db),
):
    if not idempotency_key or not idempotency_key.strip():
        raise HTTPException(
            status_code=400, detail="Idempotency-Key header must not be empty."
        )

    try:
        body, status_code, cache_hit = idempotency_service.process_payment(
            db=db,
            idempotency_key=idempotency_key,
            payment=payment,
        )
    except ConflictError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))

    response.status_code = status_code
    if cache_hit:
        response.headers["X-Cache-Hit"] = "true"

    return body
