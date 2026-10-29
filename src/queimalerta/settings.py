"""Environment-backed application settings."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _load_dotenv(path: Path) -> None:
    """Load simple KEY=VALUE pairs without overriding the process environment."""
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip("\"'"))


def _as_bool(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _database_url(value: str) -> str:
    prefix = "sqlite:///"
    if value.startswith(prefix) and not value.startswith("sqlite:////"):
        relative_path = value.removeprefix(prefix)
        absolute_path = (PROJECT_ROOT / relative_path).resolve()
        absolute_path.parent.mkdir(parents=True, exist_ok=True)
        return f"sqlite:///{absolute_path.as_posix()}"
    return value


@dataclass(frozen=True, slots=True)
class Settings:
    database_url: str
    inpe_daily_url: str
    archive_dir: Path
    refresh_seconds: int
    stale_after_minutes: int
    max_map_points: int
    host: str
    port: int
    debug: bool
    log_level: str

    @classmethod
    def from_env(cls) -> Settings:
        _load_dotenv(PROJECT_ROOT / ".env")
        archive_value = os.getenv("QUEIMALERTA_ARCHIVE_DIR", "data/raw")
        archive_dir = Path(archive_value)
        if not archive_dir.is_absolute():
            archive_dir = PROJECT_ROOT / archive_dir
        return cls(
            database_url=_database_url(
                os.getenv("QUEIMALERTA_DATABASE_URL", "sqlite:///data/queimalerta.db")
            ),
            inpe_daily_url=os.getenv(
                "QUEIMALERTA_INPE_DAILY_URL",
                "https://dataserver-coids.inpe.br/queimadas/queimadas/focos/csv/diario/Brasil/",
            ).rstrip("/")
            + "/",
            archive_dir=archive_dir.resolve(),
            refresh_seconds=max(
                15, int(os.getenv("QUEIMALERTA_REFRESH_SECONDS", "60"))
            ),
            stale_after_minutes=max(
                10, int(os.getenv("QUEIMALERTA_STALE_AFTER_MINUTES", "30"))
            ),
            max_map_points=max(
                100, int(os.getenv("QUEIMALERTA_MAX_MAP_POINTS", "5000"))
            ),
            host=os.getenv("QUEIMALERTA_HOST", "127.0.0.1"),
            port=int(os.getenv("QUEIMALERTA_PORT", "8050")),
            debug=_as_bool(os.getenv("QUEIMALERTA_DEBUG")),
            log_level=os.getenv("QUEIMALERTA_LOG_LEVEL", "INFO").upper(),
        )
