import os
from pathlib import Path

import dotenv

dotenv.load_dotenv()


class Settings:
    _root_dir = Path(__file__).resolve().parent.parent
    _default_sqlite_url = f"sqlite:///{_root_dir}/idempotency_db.db"

    DATABASE_URL: str = os.getenv("DATABASE_URL", _default_sqlite_url)


settings = Settings()
