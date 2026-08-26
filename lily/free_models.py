"""CC0-derived free-tier and local LLM preset registry for Lily.

The model list is vendored from mnfst/awesome-free-llm-apis data.json. Provider
keys are read only from the runtime environment; this module never stores them.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


_CATALOG_PATH = Path(__file__).with_name("free_models_catalog.json")


def _catalog_by_name() -> dict[str, dict[str, Any]]:
    payload = json.loads(_CATALOG_PATH.read_text(encoding="utf-8"))
    return {str(provider["name"]): provider for provider in payload.get("providers", [])}


CATALOG = _catalog_by_name()

# preset: catalog provider, auth variable, family, privacy tier, and default model.
# Native families have explicitly documented request/response adapters in model_router.py.
PRESETS: dict[str, dict[str, Any]] = {
    "aion-labs": {"provider": "Aion Labs", "env": "AION_API_KEY", "family": "openai", "tier": "hosted", "default": "aion-labs/aion-3.0-mini"},
    "cohere": {"provider": "Cohere", "env": "COHERE_API_KEY", "family": "cohere", "tier": "hosted", "default": "command-a-reasoning-08-2025"},
    "gemini": {"provider": "Google Gemini", "env": "GEMINI_API_KEY", "family": "gemini_native", "tier": "training-eligible", "default": "gemini-2.5-flash"},
    "mistral": {"provider": "Mistral AI", "env": "MISTRAL_API_KEY", "family": "openai", "tier": "training-eligible", "default": "mistral-small-2603"},
    "z-ai": {"provider": "Z AI (Zhipu AI)", "env": "ZAI_API_KEY", "family": "openai", "tier": "hosted", "default": "glm-4.7-flash"},
    "cloudflare-workers-ai": {"provider": "Cloudflare Workers AI", "env": "CLOUDFLARE_AI_API_TOKEN", "account_env": "CLOUDFLARE_ACCOUNT_ID", "family": "cloudflare", "tier": "hosted", "default": "@cf/meta/llama-3.3-70b-instruct-fp8-fast"},
    "groq": {"provider": "Groq", "env": "GROQ_API_KEY", "family": "openai", "tier": "hosted", "default": "openai/gpt-oss-20b"},
    "huggingface": {"provider": "HUGGING_FACE", "env": "HF_TOKEN", "family": "openai", "tier": "hosted", "default": "meta-llama/Llama-3.1-8B-Instruct"},
    "kilo": {"provider": "Kilo Code", "env": "KILO_API_KEY", "family": "openai", "tier": "public", "default": "kilo-auto/free", "key_optional": True},
    "llm7": {"provider": "LLM7.io", "env": "LLM7_API_KEY", "family": "openai", "tier": "public", "default": "gpt-oss:20b", "key_optional": True},
    "modelscope": {"provider": "ModelScope", "env": "MODELSCOPE_API_KEY", "family": "openai", "tier": "hosted", "default": "Qwen/Qwen3.5-27B"},
    "nvidia-nim": {"provider": "NVIDIA NIM", "env": "NVIDIA_API_KEY", "family": "openai", "tier": "hosted", "default": "openai/gpt-oss-20b"},
    "ollama-cloud": {"provider": "Ollama Cloud", "env": "OLLAMA_CLOUD_API_KEY", "family": "openai", "tier": "hosted", "default": "gpt-oss:20b", "base": "https://ollama.com/v1"},
    "openrouter-free": {"provider": "OpenRouter", "env": "OPENROUTER_API_KEY", "family": "openai", "tier": "public", "default": "openrouter/free"},
    "ovh-anonymous": {"provider": "OVHcloud AI Endpoints", "env": "OVH_AI_API_KEY", "family": "openai", "tier": "public", "default": "gpt-oss-20b", "key_optional": True},
    "siliconflow": {"provider": "SiliconFlow", "env": "SILICONFLOW_API_KEY", "family": "openai", "tier": "hosted", "default": "Qwen/Qwen3-8B"},
    "ollama-local": {"provider": None, "env": "OLLAMA_API_KEY", "family": "openai", "tier": "local", "default": "qwen3:8b", "base": "http://127.0.0.1:11434/v1", "key_optional": True},
}


def preset_names() -> tuple[str, ...]:
    return tuple(PRESETS)


def _models_for(spec: dict[str, Any]) -> list[str]:
    provider_name = spec.get("provider")
    if not provider_name or provider_name not in CATALOG:
        return [str(spec["default"])]
    models = [str(item["id"]) for item in CATALOG[provider_name].get("models", []) if item.get("id")]
    return models or [str(spec["default"])]


def profiles_for_presets(selected: tuple[str, ...], include_all_models: bool, allow_public: bool, starting_priority: int = 100) -> list[dict[str, Any]]:
    enabled = list(PRESETS) if "all" in selected else list(dict.fromkeys(selected))
    profiles: list[dict[str, Any]] = []
    priority = starting_priority
    for preset_name in enabled:
        spec = PRESETS.get(preset_name)
        if not spec or (spec["tier"] == "public" and not allow_public):
            continue
        key = os.getenv(str(spec["env"]), "")
        if not key and not spec.get("key_optional"):
            continue
        base = str(spec.get("base") or CATALOG.get(spec.get("provider"), {}).get("baseUrl") or "")
        if preset_name == "cloudflare-workers-ai":
            account_id = os.getenv(str(spec.get("account_env")), "")
            if not account_id:
                continue
            base = f"https://api.cloudflare.com/client/v4/accounts/{account_id}/ai/run"
        if preset_name == "ollama-local":
            base = os.getenv("OLLAMA_BASE_URL", base)
        if not base:
            continue
        model_override = os.getenv(f"LILY_{preset_name.upper().replace('-', '_')}_MODEL", "")
        models = _models_for(spec) if include_all_models else [model_override or str(spec["default"])]
        for model in models:
            capabilities = ["chat", "structured"] if spec["family"] in {"openai", "cohere", "gemini_native"} else ["chat"]
            if "reasoning" in model.lower() or model.startswith(("gemini-", "glm-")):
                capabilities.append("reasoning")
            profiles.append({
                "name": f"preset-{preset_name}-{model}" if include_all_models else f"preset-{preset_name}",
                "api_key": key or "local-or-anonymous",
                "base_url": base,
                "model": model,
                "family": str(spec["family"]),
                "privacy_tier": str(spec["tier"]),
                "capabilities": capabilities,
                "priority": priority,
                "max_retries": 1,
            })
            priority += 1
    return profiles
