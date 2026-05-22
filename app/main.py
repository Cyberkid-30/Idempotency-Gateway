from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .database import engine
from .models import Base
from .routes import router as payments_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    yield


app = FastAPI(
    title="Idempotency Gateway",
    description=(
        "A payment processing API that guarantees exactly-once execution. "
        "Built for FinSafe Transactions Ltd. to eliminate double-charging."
    ),
    version="1.0.0",
    lifespan=lifespan,
)


app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],
    allow_credentials=True,
)

app.include_router(payments_router, prefix="/api/v1", tags=["Payments"])


@app.get("/", summary="Welcome endpoint")
def welcome():
    """A simple welcome endpoint to verify the API is up and running."""
    return {"message": "Welcome to the Idempotency Gateway API!"}


@app.get("/api/v1/health", summary="Health check")
def health_check():
    """A simple health check endpoint to verify the API is functioning correctly."""
    return {"status": "ok", "service": "Idempotency Gateway"}
