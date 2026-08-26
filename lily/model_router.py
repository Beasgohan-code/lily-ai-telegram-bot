from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import Any

import httpx


@dataclass(frozen=True)
class ModelProfile:
    name: str
    base_url: str
    api_key: str
    model: str
    family: str = "openai"
    capabilities: frozenset[str] = frozenset({"chat", "structured", "reasoning"})
    priority: int = 100
    max_retries: int = 1

    @property
    def key_id(self) -> str:
        return f"{self.name}:{self.model}"


@dataclass
class Health:
    failures: int = 0
    successes: int = 0
    cooldown_until: float = 0.0
    last_error: str = ""
    last_latency_ms: float = 0.0

    @property
    def available(self) -> bool:
        return time.monotonic() >= self.cooldown_until


class ModelRouter:
    """Capability-aware OpenAI-compatible chat router with failover and health tracking."""

    def __init__(self, profiles: list[ModelProfile], cooldown_base: float = 8.0, cooldown_max: float = 300.0):
        self.profiles = sorted(profiles, key=lambda profile: profile.priority)
        self.health = {profile.key_id: Health() for profile in self.profiles}
        self.cooldown_base = cooldown_base
        self.cooldown_max = cooldown_max
        self._lock = asyncio.Lock()
        self._cursor = 0

    def candidates(self, requirement: str = "chat") -> list[ModelProfile]:
        eligible = [profile for profile in self.profiles if requirement in profile.capabilities or requirement == "chat" and "chat" in profile.capabilities]
        available = [profile for profile in eligible if self.health[profile.key_id].available]
        if available:
            return available
        # If every provider is cooling down, prefer the one whose cooldown expires first.
        return sorted(eligible, key=lambda profile: self.health[profile.key_id].cooldown_until)

    def _family_payload(self, profile: ModelProfile, payload: dict[str, Any]) -> dict[str, Any]:
        request = dict(payload)
        request["model"] = profile.model
        family = profile.family.lower()
        if (family in {"anthropic", "google"} or profile.model.startswith(("claude-", "gemini-"))) and "max_completion_tokens" in request and "max_tokens" not in request:
            request["max_tokens"] = request.pop("max_completion_tokens")
        elif (family == "openai" or profile.model.startswith("gpt-")) and "max_tokens" in request and "max_completion_tokens" not in request:
            request["max_completion_tokens"] = request.pop("max_tokens")
        if "reasoning" in request.pop("_requirements", set()) or request.pop("_reasoning", False):
            if family == "openai" or profile.model.startswith("gpt-"):
                request["reasoning"] = {"effort": request.pop("_reasoning_effort", "low")}
            elif family == "anthropic" or profile.model.startswith("claude-"):
                budget = int(request.pop("_thinking_budget", 1024))
                request["thinking"] = {"type": "enabled", "budget_tokens": budget}
                request["max_tokens"] = max(int(request.get("max_tokens", 0) or 0), budget + 1024)
            elif family == "google" or profile.model.startswith("gemini-"):
                request["reasoning_effort"] = request.pop("_reasoning_effort", "low")
        else:
            request.pop("_reasoning_effort", None)
            request.pop("_thinking_budget", None)
        # Token fields were normalized before reasoning so family-specific limits remain valid.
        return request

    async def _mark_failure(self, profile: ModelProfile, error: Exception) -> None:
        state = self.health[profile.key_id]
        state.failures += 1
        state.last_error = str(error)[:300]
        delay = min(self.cooldown_max, self.cooldown_base * (2 ** min(state.failures - 1, 6)))
        state.cooldown_until = time.monotonic() + delay

    async def _mark_success(self, profile: ModelProfile, latency_ms: float) -> None:
        state = self.health[profile.key_id]
        state.successes += 1
        state.failures = 0
        state.cooldown_until = 0.0
        state.last_error = ""
        state.last_latency_ms = latency_ms

    async def chat(self, payload: dict[str, Any], requirement: str = "chat") -> tuple[dict[str, Any], ModelProfile]:
        if not self.profiles:
            raise RuntimeError("No AI model profiles are configured")
        candidates = self.candidates(requirement)
        if not candidates:
            raise RuntimeError(f"No configured model supports capability: {requirement}")
        last_error: Exception | None = None
        for profile in candidates:
            request = self._family_payload(profile, payload)
            for attempt in range(profile.max_retries + 1):
                started = time.perf_counter()
                try:
                    timeout = httpx.Timeout(float(payload.get("_timeout", 45.0)), connect=10.0)
                    async with httpx.AsyncClient(timeout=timeout) as client:
                        response = await client.post(f"{profile.base_url.rstrip('/')}/chat/completions", headers={"Authorization": f"Bearer {profile.api_key}", "Content-Type": "application/json"}, json=request)
                        if response.status_code in {401, 403, 408, 409, 429} or response.status_code >= 500:
                            raise RuntimeError(f"{profile.key_id} returned HTTP {response.status_code}")
                        response.raise_for_status()
                        data = response.json()
                    await self._mark_success(profile, (time.perf_counter() - started) * 1000)
                    return data, profile
                except Exception as exc:
                    last_error = exc
                    await self._mark_failure(profile, exc)
                    if attempt < profile.max_retries:
                        await asyncio.sleep(min(2.0, 0.25 * (2**attempt)))
        raise RuntimeError(f"All configured AI models failed for {requirement}: {last_error}")

    async def status(self) -> list[dict[str, Any]]:
        result = []
        async with self._lock:
            for profile in self.profiles:
                state = self.health[profile.key_id]
                result.append({"name": profile.name, "model": profile.model, "family": profile.family, "capabilities": sorted(profile.capabilities), "priority": profile.priority, "available": state.available, "failures": state.failures, "successes": state.successes, "last_error": state.last_error, "last_latency_ms": round(state.last_latency_ms, 1)})
        return result
