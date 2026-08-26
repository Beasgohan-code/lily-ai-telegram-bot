from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


def _bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.lower() in {"1", "true", "yes", "on"}


def _int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        return default


@dataclass(frozen=True)
class Settings:
    bot_token: str = field(default_factory=lambda: os.getenv("TELEGRAM_BOT_TOKEN", ""))
    bot_api_base: str = field(default_factory=lambda: os.getenv("TELEGRAM_API_BASE", "http://127.0.0.1:8081/bot"))
    bot_file_base: str = field(default_factory=lambda: os.getenv("TELEGRAM_FILE_BASE", "http://127.0.0.1:8081/file/bot"))
    use_local_bot_api: bool = field(default_factory=lambda: _bool("TELEGRAM_LOCAL_MODE", True))
    database_url: str = field(default_factory=lambda: os.getenv("LILY_DATABASE", "data/lily.sqlite3"))
    work_dir: Path = field(default_factory=lambda: Path(os.getenv("LILY_WORK_DIR", "work")))
    download_dir: Path = field(default_factory=lambda: Path(os.getenv("LILY_DOWNLOAD_DIR", "downloads")))
    max_file_bytes: int = field(default_factory=lambda: _int("LILY_MAX_FILE_BYTES", 1_900_000_000))
    max_job_bytes: int = field(default_factory=lambda: _int("LILY_MAX_JOB_BYTES", 2_000_000_000))
    max_concurrent_jobs: int = field(default_factory=lambda: _int("LILY_MAX_CONCURRENT_JOBS", 2))
    confirmation_ttl_seconds: int = field(default_factory=lambda: _int("LILY_CONFIRMATION_TTL", 600))
    daily_request_limit: int = field(default_factory=lambda: _int("LILY_DAILY_REQUEST_LIMIT", 100))
    monthly_request_limit: int = field(default_factory=lambda: _int("LILY_MONTHLY_REQUEST_LIMIT", 3000))
    daily_bytes_limit: int = field(default_factory=lambda: _int("LILY_DAILY_BYTES_LIMIT", 2_000_000_000))
    monthly_bytes_limit: int = field(default_factory=lambda: _int("LILY_MONTHLY_BYTES_LIMIT", 25_000_000_000))
    openai_api_key: str = field(default_factory=lambda: os.getenv("OPENAI_API_KEY", ""))
    openai_api_base: str = field(default_factory=lambda: os.getenv("OPENAI_API_BASE", ""))
    ai_keys: tuple[str, ...] = field(default_factory=lambda: tuple(
        value.strip() for value in (os.getenv("LILY_AI_KEYS") or os.getenv("OPENAI_API_KEYS") or os.getenv("OPENAI_API_KEY", "")).split(",") if value.strip()
    ))
    ai_bases: tuple[str, ...] = field(default_factory=lambda: tuple(
        value.strip() for value in (os.getenv("LILY_AI_BASES") or os.getenv("OPENAI_API_BASE", "")).split(",") if value.strip()
    ))
    ai_model: str = field(default_factory=lambda: os.getenv("LILY_AI_MODEL", "gpt-5-mini"))
    ai_reasoning_effort: str = field(default_factory=lambda: os.getenv("LILY_AI_REASONING", "low"))
    permitted_download_domains: tuple[str, ...] = field(default_factory=lambda: tuple(
        d.strip().lower() for d in os.getenv("LILY_ALLOWED_DOWNLOAD_DOMAINS", "").split(",") if d.strip()
    ))
    allow_direct_media_downloads: bool = field(default_factory=lambda: _bool("LILY_ALLOW_DIRECT_MEDIA_DOWNLOADS", False))
    admin_user_ids: tuple[int, ...] = field(default_factory=lambda: tuple(
        int(v.strip()) for v in os.getenv("LILY_ADMIN_USER_IDS", "").split(",") if v.strip().lstrip("-").isdigit()
    ))

    def prepare(self) -> None:
        Path(self.database_url).parent.mkdir(parents=True, exist_ok=True)
        self.work_dir.mkdir(parents=True, exist_ok=True)
        self.download_dir.mkdir(parents=True, exist_ok=True)


settings = Settings()
