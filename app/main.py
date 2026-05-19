from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(
    title="Idempotency Gateway",
    description=(
        "A payment processing API that guarantees exactly-once execution. "
        "Built for FinSafe Transactions Ltd. to eliminate double-charging."
    ),
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
    allow_credentials=True,
)


@app.get("/health", tags=["Health"])
def health_check():
    """
    Verify that the API is running.
    """
    return {"status": "ok"}
