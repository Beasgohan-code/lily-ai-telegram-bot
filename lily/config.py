from __future__ import annotations

import json
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
    ai_profiles_json: str = field(default_factory=lambda: os.getenv("LILY_AI_PROFILES_JSON", ""))
    model_cooldown_base: float = field(default_factory=lambda: float(os.getenv("LILY_MODEL_COOLDOWN_BASE", "8")))
    model_cooldown_max: float = field(default_factory=lambda: float(os.getenv("LILY_MODEL_COOLDOWN_MAX", "300")))
    stream_public_base_url: str = field(default_factory=lambda: os.getenv("LILY_STREAM_PUBLIC_BASE_URL", "").rstrip("/"))
    stream_link_ttl_seconds: int = field(default_factory=lambda: _int("LILY_STREAM_LINK_TTL", 3600))
    stream_bind_host: str = field(default_factory=lambda: os.getenv("LILY_STREAM_BIND_HOST", "127.0.0.1"))
    stream_port: int = field(default_factory=lambda: _int("LILY_STREAM_PORT", 8090))
    web_search_max_results: int = field(default_factory=lambda: _int("LILY_WEB_SEARCH_MAX_RESULTS", 5))
    custom_emoji_id: str = field(default_factory=lambda: os.getenv("LILY_CUSTOM_EMOJI_ID", ""))
    web_search_url: str = field(default_factory=lambda: os.getenv("LILY_WEB_SEARCH_URL", "https://api.duckduckgo.com/"))
    web_search_api_key: str = field(default_factory=lambda: os.getenv("LILY_WEB_SEARCH_API_KEY", ""))
    web_search_provider: str = field(default_factory=lambda: os.getenv("LILY_WEB_SEARCH_PROVIDER", "duckduckgo"))
    stream_signing_secret: str = field(default_factory=lambda: os.getenv("LILY_STREAM_SIGNING_SECRET", ""))
    image_generation_url: str = field(default_factory=lambda: os.getenv("LILY_IMAGE_GENERATION_URL", ""))
    image_generation_api_key: str = field(default_factory=lambda: os.getenv("LILY_IMAGE_GENERATION_API_KEY", ""))
    video_generation_url: str = field(default_factory=lambda: os.getenv("LILY_VIDEO_GENERATION_URL", ""))
    video_generation_api_key: str = field(default_factory=lambda: os.getenv("LILY_VIDEO_GENERATION_API_KEY", ""))
    media_generation_timeout: int = field(default_factory=lambda: _int("LILY_MEDIA_GENERATION_TIMEOUT", 180))
    auto_rename_enabled: bool = field(default_factory=lambda: _bool("LILY_AUTO_RENAME_ENABLED", False))
    auto_rename_template: str = field(default_factory=lambda: os.getenv("LILY_AUTO_RENAME_TEMPLATE", "{title} - S{season:02d}E{episode:02d} - {quality}.{ext}"))
    permitted_download_domains: tuple[str, ...] = field(default_factory=lambda: tuple(
        d.strip().lower() for d in os.getenv("LILY_ALLOWED_DOWNLOAD_DOMAINS", "").split(",") if d.strip()
    ))
    allow_direct_media_downloads: bool = field(default_factory=lambda: _bool("LILY_ALLOW_DIRECT_MEDIA_DOWNLOADS", False))
    admin_user_ids: tuple[int, ...] = field(default_factory=lambda: tuple(
        int(v.strip()) for v in os.getenv("LILY_ADMIN_USER_IDS", "").split(",") if v.strip().lstrip("-").isdigit()
    ))

    def model_profiles(self) -> list[dict[str, object]]:
        if self.ai_profiles_json:
            try:
                raw = json.loads(self.ai_profiles_json)
                if isinstance(raw, list):
                    return [item for item in raw if isinstance(item, dict) and item.get("api_key") and item.get("base_url") and item.get("model")]
            except json.JSONDecodeError:
                pass
        keys = self.ai_keys or ((self.openai_api_key,) if self.openai_api_key else ())
        bases = self.ai_bases or ((self.openai_api_base,) if self.openai_api_base else ())
        models = tuple(value.strip() for value in os.getenv("LILY_AI_MODELS", self.ai_model).split(",") if value.strip())
        families = tuple(value.strip() for value in os.getenv("LILY_AI_FAMILIES", "").split(",") if value.strip())
        profiles = []
        for index, key in enumerate(keys):
            if not bases:
                continue
            model = models[min(index, len(models) - 1)]
            family = families[min(index, len(families) - 1)] if families else ("anthropic" if model.startswith("claude-") else "google" if model.startswith("gemini-") else "openai")
            profiles.append({"name": f"provider-{index + 1}", "api_key": key, "base_url": bases[min(index, len(bases) - 1)], "model": model, "family": family, "capabilities": ["chat", "structured", "reasoning"] if model.startswith(("gpt-", "claude-", "gemini-")) else ["chat"], "priority": index, "max_retries": 1})
        return profiles

    def prepare(self) -> None:
        Path(self.database_url).parent.mkdir(parents=True, exist_ok=True)
        self.work_dir.mkdir(parents=True, exist_ok=True)
        self.download_dir.mkdir(parents=True, exist_ok=True)


settings = Settings()
