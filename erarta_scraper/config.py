from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DEFAULT_DB_PATH = BASE_DIR / "art_market.db"
CATALOG_BASE_URL = "https://shop.erarta.com/ru/shop/catalogue/original/"


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    return default if raw is None or raw == "" else int(raw)


def _env_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    return default if raw is None or raw == "" else float(raw)


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None or raw == "":
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    db_path: Path = DEFAULT_DB_PATH
    catalog_base_url: str = CATALOG_BASE_URL
    pages_count: int = 10
    batch_size: int = 20
    page_wait_seconds: float = 10.0
    detail_wait_seconds: float = 5.0
    request_delay_seconds: float = 0.4
    retry_attempts: int = 3
    retry_backoff_seconds: float = 0.5
    headless: bool = False
    max_retries: int = 20
    report_file: str = "retry_report.csv"

    @classmethod
    def from_env(cls) -> Settings:
        db_raw = os.getenv("ERARTA_DB_PATH")
        return cls(
            db_path=Path(db_raw) if db_raw else DEFAULT_DB_PATH,
            catalog_base_url=os.getenv("ERARTA_CATALOG_URL", CATALOG_BASE_URL),
            pages_count=_env_int("ERARTA_PAGES", 10),
            batch_size=_env_int("ERARTA_BATCH_SIZE", 20),
            page_wait_seconds=_env_float("ERARTA_PAGE_WAIT", 10.0),
            detail_wait_seconds=_env_float("ERARTA_DETAIL_WAIT", 5.0),
            request_delay_seconds=_env_float("ERARTA_REQUEST_DELAY", 0.4),
            retry_attempts=_env_int("ERARTA_RETRY_ATTEMPTS", 3),
            retry_backoff_seconds=_env_float("ERARTA_RETRY_BACKOFF", 0.5),
            headless=_env_bool("ERARTA_HEADLESS", False),
            max_retries=_env_int("ERARTA_MAX_RETRIES", 20),
            report_file=os.getenv("ERARTA_REPORT_FILE", "retry_report.csv"),
        )
