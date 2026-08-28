from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path

from .free_models import profiles_for_presets


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
    enable_agent_team: bool = field(default_factory=lambda: _bool("LILY_ENABLE_AGENT_TEAM", False))
    agent_team_max_roles: int = field(default_factory=lambda: max(1, min(_int("LILY_AGENT_TEAM_MAX_ROLES", 3), 4)))
    agent_team_timeout_seconds: int = field(default_factory=lambda: max(5, min(_int("LILY_AGENT_TEAM_TIMEOUT", 20), 60)))
    enable_rag_routing: bool = field(default_factory=lambda: _bool("LILY_ENABLE_RAG_ROUTING", True))
    enable_deep_research: bool = field(default_factory=lambda: _bool("LILY_ENABLE_DEEP_RESEARCH", True))
    deep_research_scouts: int = field(default_factory=lambda: max(1, min(_int("LILY_DEEP_RESEARCH_SCOUTS", 3), 4)))
    enable_qa_loop: bool = field(default_factory=lambda: _bool("LILY_ENABLE_QA_LOOP", True))
    enable_scenario_runbooks: bool = field(default_factory=lambda: _bool("LILY_ENABLE_SCENARIO_RUNBOOKS", True))
    ai_profiles_json: str = field(default_factory=lambda: os.getenv("LILY_AI_PROFILES_JSON", ""))
    ai_presets: tuple[str, ...] = field(default_factory=lambda: tuple(value.strip().lower() for value in os.getenv("LILY_AI_PRESETS", "").split(",") if value.strip()))
    enable_all_catalog_models: bool = field(default_factory=lambda: _bool("LILY_ENABLE_ALL_CATALOG_MODELS", False))
    allow_public_ai_fallbacks: bool = field(default_factory=lambda: _bool("LILY_ALLOW_PUBLIC_AI_FALLBACKS", False))
    fallback_order: tuple[str, ...] = field(default_factory=lambda: tuple(value.strip().lower() for value in os.getenv("LILY_FALLBACK_ORDER", "free,gemini,openai,groq").split(",") if value.strip()))
    model_cooldown_base: float = field(default_factory=lambda: float(os.getenv("LILY_MODEL_COOLDOWN_BASE", "8")))
    model_cooldown_max: float = field(default_factory=lambda: float(os.getenv("LILY_MODEL_COOLDOWN_MAX", "300")))
    stream_public_base_url: str = field(default_factory=lambda: os.getenv("LILY_STREAM_PUBLIC_BASE_URL", "").rstrip("/"))
    stream_link_ttl_seconds: int = field(default_factory=lambda: _int("LILY_STREAM_LINK_TTL", 3600))
    stream_bind_host: str = field(default_factory=lambda: os.getenv("LILY_STREAM_BIND_HOST", "127.0.0.1"))
    stream_port: int = field(default_factory=lambda: _int("LILY_STREAM_PORT", 8090))
    stream_embedded: bool = field(default_factory=lambda: _bool("LILY_STREAM_EMBEDDED", True))
    rich_live_previews: bool = field(default_factory=lambda: _bool("LILY_RICH_LIVE_PREVIEWS", True))
    rich_visible_progress: bool = field(default_factory=lambda: _bool("LILY_RICH_VISIBLE_PROGRESS", True))
    rich_button_styles: bool = field(default_factory=lambda: _bool("LILY_RICH_BUTTON_STYLES", True))
    enable_miniapp_bridge: bool = field(default_factory=lambda: _bool("LILY_ENABLE_MINIAPP_BRIDGE", False))
    miniapp_allowed_origins: tuple[str, ...] = field(default_factory=lambda: tuple(value.strip().rstrip("/") for value in os.getenv("LILY_MINIAPP_ALLOWED_ORIGINS", "").split(",") if value.strip().startswith("https://")))
    miniapp_init_data_ttl_seconds: int = field(default_factory=lambda: max(60, min(_int("LILY_MINIAPP_INIT_DATA_TTL", 3600), 86_400)))
    web_search_max_results: int = field(default_factory=lambda: _int("LILY_WEB_SEARCH_MAX_RESULTS", 5))
    custom_emoji_id: str = field(default_factory=lambda: os.getenv("LILY_CUSTOM_EMOJI_ID", ""))
    web_search_url: str = field(default_factory=lambda: os.getenv("LILY_WEB_SEARCH_URL", "https://api.duckduckgo.com/"))
    web_search_api_key: str = field(default_factory=lambda: os.getenv("LILY_WEB_SEARCH_API_KEY", ""))
    web_search_provider: str = field(default_factory=lambda: os.getenv("LILY_WEB_SEARCH_PROVIDER", "duckduckgo"))
    stream_signing_secret: str = field(default_factory=lambda: os.getenv("LILY_STREAM_SIGNING_SECRET", ""))
    projects_root: Path = field(default_factory=lambda: Path(os.getenv("LILY_PROJECTS_ROOT", "projects")))
    project_env_root: Path = field(default_factory=lambda: Path(os.getenv("LILY_PROJECT_ENV_ROOT", "project-env")))
    allowed_project_repositories: tuple[str, ...] = field(default_factory=lambda: tuple(value.strip().lower().rstrip("/") for value in os.getenv("LILY_ALLOWED_PROJECT_REPOSITORIES", "").split(",") if value.strip()))
    bot_factory_dry_run: bool = field(default_factory=lambda: _bool("LILY_BOT_FACTORY_DRY_RUN", True))
    enable_managed_project_provisioning: bool = field(default_factory=lambda: _bool("LILY_ENABLE_MANAGED_PROJECT_PROVISIONING", False))
    enable_managed_service_supervisor: bool = field(default_factory=lambda: _bool("LILY_ENABLE_MANAGED_SERVICE_SUPERVISOR", False))
    allowed_managed_service_slugs: tuple[str, ...] = field(default_factory=lambda: tuple(value.strip().lower() for value in os.getenv("LILY_ALLOWED_MANAGED_SERVICES", "").split(",") if value.strip()))
    image_generation_url: str = field(default_factory=lambda: os.getenv("LILY_IMAGE_GENERATION_URL", ""))
    image_generation_api_key: str = field(default_factory=lambda: os.getenv("LILY_IMAGE_GENERATION_API_KEY", ""))
    video_generation_url: str = field(default_factory=lambda: os.getenv("LILY_VIDEO_GENERATION_URL", ""))
    video_generation_api_key: str = field(default_factory=lambda: os.getenv("LILY_VIDEO_GENERATION_API_KEY", ""))
    speech_generation_url: str = field(default_factory=lambda: os.getenv("LILY_SPEECH_GENERATION_URL", ""))
    speech_generation_api_key: str = field(default_factory=lambda: os.getenv("LILY_SPEECH_GENERATION_API_KEY", ""))
    speech_voice: str = field(default_factory=lambda: os.getenv("LILY_SPEECH_VOICE", "Kore"))
    speech_max_chars: int = field(default_factory=lambda: max(100, min(_int("LILY_SPEECH_MAX_CHARS", 1800), 6000)))
    media_generation_timeout: int = field(default_factory=lambda: _int("LILY_MEDIA_GENERATION_TIMEOUT", 180))
    auto_rename_enabled: bool = field(default_factory=lambda: _bool("LILY_AUTO_RENAME_ENABLED", False))
    auto_rename_template: str = field(default_factory=lambda: os.getenv("LILY_AUTO_RENAME_TEMPLATE", "{title} - S{season:02d}E{episode:02d} - {quality}.{ext}"))
    permitted_download_domains: tuple[str, ...] = field(default_factory=lambda: tuple(
        d.strip().lower() for d in os.getenv("LILY_ALLOWED_DOWNLOAD_DOMAINS", "").split(",") if d.strip()
    ))
    allow_direct_media_downloads: bool = field(default_factory=lambda: _bool("LILY_ALLOW_DIRECT_MEDIA_DOWNLOADS", False))
    allowed_chapter_domains: tuple[str, ...] = field(default_factory=lambda: tuple(
        d.strip().lower() for d in os.getenv("LILY_ALLOWED_CHAPTER_DOMAINS", "").split(",") if d.strip()
    ))
    allow_direct_chapter_downloads: bool = field(default_factory=lambda: _bool("LILY_ALLOW_DIRECT_CHAPTER_DOWNLOADS", False))
    enable_mangadex_metadata: bool = field(default_factory=lambda: _bool("LILY_ENABLE_MANGADEX_METADATA", False))
    mangadex_user_agent: str = field(default_factory=lambda: os.getenv("LILY_MANGADEX_USER_AGENT", ""))
    mangadex_min_interval_seconds: float = field(default_factory=lambda: max(0.25, float(os.getenv("LILY_MANGADEX_MIN_INTERVAL_SECONDS", "0.3"))))
    mangadex_cache_seconds: int = field(default_factory=lambda: _int("LILY_MANGADEX_CACHE_SECONDS", 300))
    admin_user_ids: tuple[int, ...] = field(default_factory=lambda: tuple(
        int(v.strip()) for v in os.getenv("LILY_ADMIN_USER_IDS", "").split(",") if v.strip().lstrip("-").isdigit()
    ))

    def model_profiles(self) -> list[dict[str, object]]:
        profiles: list[dict[str, object]] = []
        if self.ai_profiles_json:
            try:
                raw = json.loads(self.ai_profiles_json)
                if isinstance(raw, list):
                    profiles.extend(item for item in raw if isinstance(item, dict) and item.get("api_key") and item.get("base_url") and item.get("model"))
            except json.JSONDecodeError:
                pass
        keys = self.ai_keys or ((self.openai_api_key,) if self.openai_api_key else ())
        bases = self.ai_bases or ((self.openai_api_base,) if self.openai_api_base else ())
        models = tuple(value.strip() for value in os.getenv("LILY_AI_MODELS", self.ai_model).split(",") if value.strip())
        families = tuple(value.strip() for value in os.getenv("LILY_AI_FAMILIES", "").split(",") if value.strip())
        for index, key in enumerate(keys):
            if not bases:
                continue
            model = models[min(index, len(models) - 1)]
            family = families[min(index, len(families) - 1)] if families else ("anthropic" if model.startswith("claude-") else "google" if model.startswith("gemini-") else "openai")
            profiles.append({"name": f"provider-{index + 1}", "api_key": key, "base_url": bases[min(index, len(bases) - 1)], "model": model, "family": family, "capabilities": ["chat", "structured", "reasoning"] if model.startswith(("gpt-", "claude-", "gemini-")) else ["chat"], "priority": index, "max_retries": 1})
        profiles.extend(profiles_for_presets(self.ai_presets, self.enable_all_catalog_models, self.allow_public_ai_fallbacks, starting_priority=len(profiles)))
        tier_rank = {tier: index for index, tier in enumerate(self.fallback_order)}

        def tier(profile: dict[str, object]) -> str:
            name = str(profile.get("name", "")).lower()
            base = str(profile.get("base_url", "")).lower()
            if name.startswith("preset-groq"):
                return "groq"
            if name.startswith("preset-gemini") or "gemini" in str(profile.get("model", "")).lower():
                return "gemini"
            if name.startswith("preset-"):
                return "free"
            if "api.openai.com" in base or str(profile.get("family", "")).lower() == "openai":
                return "openai"
            return "openai"

        ordered = sorted(enumerate(profiles), key=lambda pair: (tier_rank.get(tier(pair[1]), len(tier_rank)), pair[0]))
        return [{**profile, "priority": index} for index, (_, profile) in enumerate(ordered)]

    def prepare(self) -> None:
        Path(self.database_url).parent.mkdir(parents=True, exist_ok=True)
        self.work_dir.mkdir(parents=True, exist_ok=True)
        self.download_dir.mkdir(parents=True, exist_ok=True)
        self.projects_root.mkdir(parents=True, exist_ok=True)
        self.project_env_root.mkdir(parents=True, exist_ok=True)


settings = Settings()
