from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    DATABASE_URL: str = ""
    IDEMPOTENCY_KEY_TTL_HOURS: int = 24

    model_config = {"env_file": ".env"}


settings = Settings()
