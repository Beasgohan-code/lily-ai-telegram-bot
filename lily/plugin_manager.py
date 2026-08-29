from __future__ import annotations

import importlib.util
import inspect
import re
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType
from typing import Any

from .agent import ACTIONS, Plan


@dataclass(frozen=True)
class PluginContext:
    text: str
    chat_id: int
    user_id: int
    reply_message_id: int | None = None


@dataclass
class LoadedPlugin:
    module: ModuleType
    manifest: dict[str, Any]

    @property
    def name(self) -> str:
        return str(self.manifest["name"])


class PluginManager:
    """Loads only trusted local plugins and converts them into Lily Plans.

    Plugins may return a Plan or a dictionary matching Plan.from_dict(). They do not
    receive a Telegram Bot object; dangerous operations must go through Lily's normal
    permission and confirmation layer.
    """

    def __init__(self, directory: str = "plugins") -> None:
        self.directory = Path(directory)
        self.plugins: dict[str, LoadedPlugin] = {}

    def discover(self) -> list[str]:
        self.plugins.clear()
        self.directory.mkdir(parents=True, exist_ok=True)
        for path in sorted(self.directory.glob("*.py")):
            if path.name.startswith("_"):
                continue
            try:
                module_name = f"lily_custom_plugin_{path.stem}"
                spec = importlib.util.spec_from_file_location(module_name, path)
                if not spec or not spec.loader:
                    continue
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)
                manifest = getattr(module, "PLUGIN", None)
                self._validate_manifest(manifest)
                self.plugins[str(manifest["name"])] = LoadedPlugin(module, manifest)
            except Exception:
                # A bad optional plugin must not prevent Lily from starting.
                continue
        return sorted(self.plugins)

    def _validate_manifest(self, manifest: Any) -> None:
        if not isinstance(manifest, dict):
            raise ValueError("PLUGIN must be a dictionary")
        for field in ("name", "version", "description", "triggers", "action"):
            if field not in manifest:
                raise ValueError(f"Plugin manifest missing {field}")
        if not isinstance(manifest["triggers"], list) or not manifest["triggers"]:
            raise ValueError("Plugin triggers must be a non-empty list")
        if str(manifest["action"]) not in ACTIONS:
            raise ValueError("Plugin action is not in Lily's allow-list")
        if str(manifest.get("risk", "safe")) not in {"safe", "risky", "dangerous"}:
            raise ValueError("Plugin risk is invalid")

    def _matches(self, manifest: dict[str, Any], text: str) -> bool:
        mode = str(manifest.get("match", "contains"))
        for trigger in manifest["triggers"]:
            try:
                if mode == "regex" and re.search(str(trigger), text, re.IGNORECASE):
                    return True
                if mode != "regex" and str(trigger).lower() in text.lower():
                    return True
            except re.error:
                continue
        return False

    async def plan(self, text: str, chat_id: int, user_id: int, reply_message_id: int | None = None) -> Plan | None:
        context = PluginContext(text, chat_id, user_id, reply_message_id)
        for loaded in self.plugins.values():
            if not self._matches(loaded.manifest, text):
                continue
            builder = getattr(loaded.module, "build_plan", None)
            if builder:
                value = builder(context)
                if inspect.isawaitable(value):
                    value = await value
                plan = value if isinstance(value, Plan) else Plan.from_dict(value if isinstance(value, dict) else {})
            else:
                plan = Plan(
                    intent=loaded.name,
                    summary=str(loaded.manifest["description"]),
                    action=str(loaded.manifest["action"]),
                    risk=str(loaded.manifest.get("risk", "safe")),
                    requires_confirmation=bool(loaded.manifest.get("requires_confirmation", False)),
                    args=dict(loaded.manifest.get("args", {})),
                    confidence=1.0,
                )
            if plan.intent == "none":
                plan.intent = loaded.name
            return plan
        return None

    def list(self) -> list[dict[str, Any]]:
        return [{"name": plugin.name, "version": plugin.manifest["version"], "description": plugin.manifest["description"], "action": plugin.manifest["action"], "risk": plugin.manifest.get("risk", "safe")} for plugin in self.plugins.values()]


plugin_manager = PluginManager()
plugin_manager.discover()
