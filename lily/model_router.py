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
    privacy_tier: str = "hosted"

    @property
    def key_id(self) -> str:
        return f"{self.name}:{self.model}"


@dataclass
class Health:
    failures: int = 0
    successes: int = 0
    in_flight: int = 0
    cooldown_until: float = 0.0
    last_error: str = ""
    last_latency_ms: float = 0.0
    # Observability aggregates (in-memory cumulative since process start).
    prompt_tokens: int = 0
    completion_tokens: int = 0
    error_counts: dict[str, int] = field(default_factory=dict)

    @property
    def available(self) -> bool:
        return time.monotonic() >= self.cooldown_until

    @property
    def total_tokens(self) -> int:
        return self.prompt_tokens + self.completion_tokens


class ModelRouter:
    """Capability-aware OpenAI-compatible chat router with failover and health tracking."""

    def __init__(self, profiles: list[ModelProfile], cooldown_base: float = 8.0, cooldown_max: float = 300.0, transport: httpx.AsyncBaseTransport | None = None):
        self.profiles = sorted(profiles, key=lambda profile: profile.priority)
        self.health = {profile.key_id: Health() for profile in self.profiles}
        self.cooldown_base = cooldown_base
        self.cooldown_max = cooldown_max
        self.transport = transport
        self._lock = asyncio.Lock()
        self._cursor = 0
        self._client: httpx.AsyncClient | None = None

    def _http(self) -> httpx.AsyncClient:
        """Return a shared, connection-pooled AsyncClient.

        Opening an AsyncClient on every chat request forces a fresh TCP+TLS
        handshake per LLM call, which dominates latency and defeats keep-alive.
        `Limits` ups the pool so parallel requests (agent team, scouts) can
        reuse connections instead of serialising on a single one.
        """
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(60.0, connect=10.0),
                limits=httpx.Limits(max_connections=32, max_keepalive_connections=16),
                transport=self.transport,
            )
        return self._client

    async def aclose(self) -> None:
        """Close the shared connection pool (called during application shutdown)."""
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    def _eligible(self, requirement: str, allow_public: bool, attempted: set[str] | None = None) -> list[ModelProfile]:
        eligible = [profile for profile in self.profiles if requirement in profile.capabilities or requirement == "chat" and "chat" in profile.capabilities]
        if not allow_public:
            eligible = [profile for profile in eligible if profile.privacy_tier != "public"]
        if attempted:
            eligible = [profile for profile in eligible if profile.key_id not in attempted]
        return eligible

    def candidates(self, requirement: str = "chat", allow_public: bool = False) -> list[ModelProfile]:
        eligible = self._eligible(requirement, allow_public)
        available = [profile for profile in eligible if self.health[profile.key_id].available]
        if available:
            return available
        # If every provider is cooling down, prefer the one whose cooldown expires first.
        return sorted(eligible, key=lambda profile: self.health[profile.key_id].cooldown_until)

    async def _reserve_candidate(self, requirement: str, allow_public: bool, attempted: set[str]) -> ModelProfile:
        """Reserve one profile so an initial 429 cannot fan out into a request storm."""
        while True:
            async with self._lock:
                eligible = self._eligible(requirement, allow_public, attempted)
                if not eligible:
                    raise RuntimeError(f"No configured model supports capability: {requirement}")
                available = [profile for profile in eligible if self.health[profile.key_id].available and self.health[profile.key_id].in_flight == 0]
                if available:
                    profile = available[0]
                    self.health[profile.key_id].in_flight += 1
                    return profile
                now = time.monotonic()
                waits = [max(0.01, self.health[profile.key_id].cooldown_until - now) for profile in eligible if self.health[profile.key_id].in_flight == 0]
            # A short, bounded yield lets an in-flight probe publish health before another request is sent.
            await asyncio.sleep(min(waits) if waits else 0.01)

    async def _release(self, profile: ModelProfile) -> None:
        async with self._lock:
            state = self.health[profile.key_id]
            state.in_flight = max(0, state.in_flight - 1)

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

    @staticmethod
    def _classify_error(error: Exception) -> str:
        """Classify a provider error into a coarse, aggregate-safe bucket."""
        message = str(error).lower()
        if "http 429" in message or "rate limit" in message or "quota" in message or "too many" in message:
            return "rate_limit"
        if "http 401" in message or "http 403" in message or "unauthorized" in message or "api key" in message or "authentication" in message or "invalid key" in message:
            return "auth"
        if isinstance(error, httpx.TimeoutException) or "timeout" in message or "timed out" in message:
            return "timeout"
        if "http 5" in message or "500" in message or "502" in message or "503" in message or "504" in message or "server" in message or "bad gateway" in message or "service unavailable" in message:
            return "server"
        if "404" in message or "not found" in message or "json" in message or "invalid-json" in message or "malformed" in message or "decode" in message:
            return "malformed"
        if isinstance(error, httpx.NetworkError) or "connect" in message or "connection" in message:
            return "network"
        return "other"

    @staticmethod
    def _token_usage(data: dict[str, Any]) -> tuple[int, int]:
        """Pull prompt/completion token counts from a provider response, if present."""
        usage = data.get("usage") or {}
        if not isinstance(usage, dict):
            return 0, 0
        prompt = int(usage.get("prompt_tokens", 0) or 0)
        completion = int(usage.get("completion_tokens", 0) or 0)
        if not prompt and not completion:
            prompt = int(usage.get("input_tokens", 0) or 0)
            completion = int(usage.get("output_tokens", 0) or 0)
        return prompt, completion

    async def _mark_failure(self, profile: ModelProfile, error: Exception) -> None:
        state = self.health[profile.key_id]
        state.failures += 1
        error_class = self._classify_error(error)
        state.error_counts[error_class] = state.error_counts.get(error_class, 0) + 1
        state.last_error = str(error)[:300]
        delay = min(self.cooldown_max, self.cooldown_base * (2 ** min(state.failures - 1, 6)))
        state.cooldown_until = time.monotonic() + delay

    async def _mark_success(self, profile: ModelProfile, latency_ms: float, data: dict[str, Any] | None = None) -> None:
        state = self.health[profile.key_id]
        state.successes += 1
        state.failures = 0
        state.cooldown_until = 0.0
        state.last_error = ""
        state.last_latency_ms = latency_ms
        if data is not None:
            prompt, completion = self._token_usage(data)
            state.prompt_tokens += prompt
            state.completion_tokens += completion

    @staticmethod
    def _plain_messages(messages: list[dict[str, Any]]) -> str:
        return "\n\n".join(f"{str(message.get('role', 'user')).upper()}: {message.get('content', '')}" for message in messages)

    def _cohere_request(self, profile: ModelProfile, payload: dict[str, Any]) -> tuple[str, dict[str, str], dict[str, Any]]:
        request = self._family_payload(profile, payload)
        request.pop("max_completion_tokens", None)
        request["max_tokens"] = int(payload.get("max_completion_tokens", payload.get("max_tokens", 1200)))
        response_format = request.pop("response_format", None)
        if isinstance(response_format, dict) and response_format.get("type") == "json_schema":
            schema = response_format.get("json_schema", {}).get("schema", {})
            request["response_format"] = {"type": "json_object", "json_schema": schema}
        request["stream"] = False
        return f"{profile.base_url.rstrip('/')}/chat", {"Authorization": f"Bearer {profile.api_key}", "Content-Type": "application/json"}, request

    def _gemini_request(self, profile: ModelProfile, payload: dict[str, Any]) -> tuple[str, dict[str, str], dict[str, Any]]:
        system_messages = [str(message.get("content", "")) for message in payload.get("messages", []) if message.get("role") == "system"]
        contents = [{"role": "model" if message.get("role") == "assistant" else "user", "parts": [{"text": str(message.get("content", ""))}]} for message in payload.get("messages", []) if message.get("role") != "system"]
        generation: dict[str, Any] = {"maxOutputTokens": int(payload.get("max_completion_tokens", payload.get("max_tokens", 1200)))}
        if isinstance(payload.get("response_format"), dict):
            generation["responseMimeType"] = "application/json"
        request: dict[str, Any] = {"contents": contents, "generationConfig": generation}
        if system_messages:
            request["systemInstruction"] = {"parts": [{"text": "\n".join(system_messages)}]}
        endpoint = f"{profile.base_url.rstrip('/')}/models/{profile.model}:generateContent?key={profile.api_key}"
        return endpoint, {"Content-Type": "application/json"}, request

    def _cloudflare_request(self, profile: ModelProfile, payload: dict[str, Any]) -> tuple[str, dict[str, str], dict[str, Any]]:
        endpoint = f"{profile.base_url.rstrip('/')}/{profile.model}"
        return endpoint, {"Authorization": f"Bearer {profile.api_key}", "Content-Type": "application/json"}, {"prompt": self._plain_messages(payload.get("messages", []))}

    @staticmethod
    def _normalize_response(profile: ModelProfile, response: dict[str, Any]) -> dict[str, Any]:
        if profile.family == "cohere":
            blocks = response.get("message", {}).get("content", [])
            text = "".join(str(block.get("text", "")) for block in blocks if isinstance(block, dict))
            return {"choices": [{"message": {"content": text}}], "provider_response": response}
        if profile.family == "gemini_native":
            parts = response.get("candidates", [{}])[0].get("content", {}).get("parts", [])
            text = "".join(str(part.get("text", "")) for part in parts if isinstance(part, dict))
            return {"choices": [{"message": {"content": text}}], "provider_response": response}
        if profile.family == "cloudflare":
            text = str(response.get("result", {}).get("response", ""))
            return {"choices": [{"message": {"content": text}}], "provider_response": response}
        return response

    def _endpoint(self, profile: ModelProfile, payload: dict[str, Any]) -> tuple[str, dict[str, str], dict[str, Any]]:
        if profile.family == "cohere":
            return self._cohere_request(profile, payload)
        if profile.family == "gemini_native":
            return self._gemini_request(profile, payload)
        if profile.family == "cloudflare":
            return self._cloudflare_request(profile, payload)
        return f"{profile.base_url.rstrip('/')}/chat/completions", {"Authorization": f"Bearer {profile.api_key}", "Content-Type": "application/json"}, self._family_payload(profile, payload)

    async def chat(self, payload: dict[str, Any], requirement: str = "chat") -> tuple[dict[str, Any], ModelProfile]:
        if not self.profiles:
            raise RuntimeError("No AI model profiles are configured")
        allow_public = bool(payload.get("_allow_public_fallback", False))
        if not self._eligible(requirement, allow_public):
            raise RuntimeError(f"No configured model supports capability: {requirement}")
        last_error: Exception | None = None
        attempted: set[str] = set()
        while True:
            try:
                profile = await self._reserve_candidate(requirement, allow_public, attempted)
            except RuntimeError:
                break
            endpoint, headers, request = self._endpoint(profile, payload)
            client = self._http()
            try:
                for attempt in range(profile.max_retries + 1):
                    started = time.perf_counter()
                    try:
                        timeout = httpx.Timeout(float(payload.get("_timeout", 45.0)), connect=10.0)
                        response = await client.post(endpoint, headers=headers, json=request, timeout=timeout)
                        if response.status_code in {401, 403, 408, 409, 429} or response.status_code >= 500:
                            raise RuntimeError(f"{profile.key_id} returned HTTP {response.status_code}")
                        response.raise_for_status()
                        data = self._normalize_response(profile, response.json())
                        await self._mark_success(profile, (time.perf_counter() - started) * 1000, data)
                        return data, profile
                    except Exception as exc:
                        last_error = exc
                        await self._mark_failure(profile, exc)
                        # A rate limit is already a clear provider-health signal; fail over instead of retrying it immediately.
                        if "HTTP 429" in str(exc) or attempt >= profile.max_retries:
                            break
                        await asyncio.sleep(min(2.0, 0.25 * (2**attempt)))
            finally:
                await self._release(profile)
            attempted.add(profile.key_id)
        raise RuntimeError(f"All configured AI models failed for {requirement}: {last_error}")

    async def status(self) -> list[dict[str, Any]]:
        result = []
        async with self._lock:
            for profile in self.profiles:
                state = self.health[profile.key_id]
                result.append({"name": profile.name, "model": profile.model, "family": profile.family, "privacy_tier": profile.privacy_tier, "capabilities": sorted(profile.capabilities), "priority": profile.priority, "available": state.available, "in_flight": state.in_flight, "failures": state.failures, "successes": state.successes, "last_error": state.last_error, "last_latency_ms": round(state.last_latency_ms, 1), "prompt_tokens": state.prompt_tokens, "completion_tokens": state.completion_tokens, "total_tokens": state.total_tokens, "error_classes": dict(state.error_counts)})
        return result

    async def telemetry(self) -> list[dict[str, Any]]:
        """Return per-profile aggregate metrics for persistence (no prompts/secrets)."""
        result = []
        async with self._lock:
            for profile in self.profiles:
                state = self.health[profile.key_id]
                result.append({
                    "name": profile.name,
                    "model": profile.model,
                    "family": profile.family,
                    "privacy_tier": profile.privacy_tier,
                    "successes": state.successes,
                    "failures": state.failures,
                    "prompt_tokens": state.prompt_tokens,
                    "completion_tokens": state.completion_tokens,
                    "error_classes": dict(state.error_counts),
                })
        return result

    async def reset_telemetry(self) -> None:
        """Zero the in-memory provider aggregates after they are flushed to storage."""
        async with self._lock:
            for state in self.health.values():
                state.prompt_tokens = 0
                state.completion_tokens = 0
                state.error_counts = dict()
