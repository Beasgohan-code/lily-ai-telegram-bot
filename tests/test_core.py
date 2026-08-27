from __future__ import annotations

import asyncio
import tempfile
import unittest
from collections import Counter
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

import httpx

from lily.agent import AIClient
from lily.model_router import ModelProfile, ModelRouter
from lily.plugin_manager import plugin_manager
from lily.db import Database
from lily.postbot import ChannelPostService
from lily.pagination import PaginationManager
from lily.rich import confirmation_keyboard
from lily.tools import safe_filename
import lily.web_media as web_media
from lily.web_media import stream_links
from lily.config import settings
from lily.free_models import CATALOG, PRESETS
from lily.group_controls import GROUP_CONTROLS, GROUP_CONTROL_MAP


class LilyCoreTests(unittest.TestCase):
    def test_safe_filename_blocks_paths(self):
        self.assertEqual(safe_filename("../../secret.txt"), "secret.txt")
        self.assertNotIn("/", safe_filename("a/b:c?.txt"))

    def test_rich_confirmation_payload(self):
        payload = confirmation_keyboard("abc")
        self.assertEqual(payload["inline_keyboard"][0][0]["callback_data"], "confirm:abc:yes")

    def test_anime_announcement_has_rich_blocks_and_primary_buttons(self):
        blocks = ChannelPostService().announcement_blocks({
            "title": "Dragon Ball",
            "type": "TV",
            "rating": "8.5/10",
            "status": "Finished",
            "episodes": 153,
            "genres": "Action, Adventure",
            "plot": "A synopsis.",
            "anilist_id": 1,
        })
        kinds = [block["type"] for block in blocks]
        self.assertIn("paragraph", kinds)  # The title is represented in a bold rich text paragraph.
        self.assertIn("expandable_blockquote", kinds)
        buttons = next(block for block in blocks if block["type"] == "buttons")
        self.assertEqual(buttons["buttons"][0]["style"], "primary")

    def test_fallback_provider_configuration_is_supported(self):
        from lily.config import Settings
        configured = Settings()
        self.assertIsInstance(configured.ai_keys, tuple)
        self.assertIsInstance(configured.ai_bases, tuple)

    def test_curated_preset_profiles_skip_missing_hosted_keys(self):
        preset_settings = replace(settings, ai_profiles_json="", ai_keys=(), ai_bases=(), openai_api_key="", openai_api_base="", ai_presets=("groq", "ollama-local", "ovh-anonymous"), allow_public_ai_fallbacks=False)
        with patch.dict("os.environ", {"GROQ_API_KEY": "", "OLLAMA_BASE_URL": "http://127.0.0.1:11434/v1", "OLLAMA_MODEL": "qwen3:8b"}, clear=False):
            profiles = preset_settings.model_profiles()
        names = {str(profile["name"]) for profile in profiles}
        self.assertNotIn("preset-groq", names)
        self.assertIn("preset-ollama-local", names)
        self.assertNotIn("preset-ovh-anonymous", names)

    def test_heuristic_router_understands_channel_post(self):
        plan = AIClient().heuristic_plan("make an anime episode announcement for Dragon Ball", {})
        self.assertEqual(plan.action, "start_channel_post")

    def test_heuristic_router_reads_numeric_target_from_plain_text(self):
        plan = AIClient().heuristic_plan("Lily, demote user 123456789", {"chat_type": "cli", "reply": {}})
        self.assertEqual(plan.action, "demote_user")
        self.assertEqual(plan.args["user_id"], 123456789)

    def test_signed_stream_link_resolves_lily_managed_file(self):
        async def run():
            with tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                updated_settings = replace(settings, stream_public_base_url="https://lily.example.test", stream_signing_secret="test-signing-secret", work_dir=root / "work", download_dir=root / "downloads")
                database = Database(str(root / "lily.sqlite3"))
                with patch.object(web_media, "settings", updated_settings), patch.object(web_media, "db", database):
                    await database.init()
                    updated_settings.work_dir.mkdir(parents=True, exist_ok=True)
                    path = updated_settings.work_dir / "stream_test.bin"
                    path.write_bytes(b"lily")
                    link = await stream_links.create(path, 99)
                    token = link.rsplit("/", 1)[-1]
                    self.assertEqual(await stream_links.resolve(token), path.resolve())
        asyncio.run(run())

    def test_moderation_state_and_post_search_persist(self):
        async def run():
            with tempfile.TemporaryDirectory() as directory:
                database = Database(str(Path(directory) / "moderation.sqlite3"))
                await database.init()
                await database.save_filter(1, 7, "scam", "Please avoid scams", True, True)
                self.assertEqual((await database.list_filters(1))[0]["trigger"], "scam")
                await database.set_lock(1, "links", True)
                self.assertTrue((await database.get_locks(1))["links"])
                await database.save_note(1, 7, "rules", "Be kind")
                self.assertEqual((await database.get_notes(1, "rules"))[0]["content"], "Be kind")
                await database.index_post("-1001", 42, "Dragon Ball", "Episode announcement", "https://t.me/c/1/42")
                self.assertEqual((await database.search_posts("-1001", "dragon"))[0]["message_id"], 42)
        asyncio.run(run())

    def test_pagination_pages_and_keyboard(self):
        manager = PaginationManager()
        session = manager.create(7, 1, "dragon", [{"title": f"Result {i}", "message_id": i} for i in range(12)], page_size=5)
        self.assertEqual(session.pages, 3)
        self.assertEqual(len(session.current()), 5)
        self.assertIn("search:", str(manager.keyboard(session)))
        session.page = 2
        self.assertEqual(len(session.current()), 2)

    def test_persistent_encoding_job_transitions(self):
        async def run():
            with tempfile.TemporaryDirectory() as directory:
                database = Database(str(Path(directory) / "queue.sqlite3"))
                await database.init()
                await database.create_encoding_job("abc123", 1, 7, {"action": "encode_media"})
                await database.update_encoding_job("abc123", state="running", progress="50%")
                item = await database.get_encoding_job("abc123")
                self.assertEqual(item["state"], "running")
                self.assertEqual(item["progress"], "50%")
                await database.update_encoding_job("abc123", state="completed", progress="Completed")
                self.assertEqual((await database.get_encoding_job("abc123"))["state"], "completed")
        asyncio.run(run())

    def test_model_family_payload_shapes_tokens_and_reasoning(self):
        router = ModelRouter([ModelProfile("claude", "https://example.test", "key", "claude-sonnet-4-6", "anthropic", frozenset({"chat", "structured", "reasoning"}))])
        payload = router._family_payload(ModelProfile("claude", "https://example.test", "key", "claude-sonnet-4-6", "anthropic", frozenset({"chat", "structured", "reasoning"})), {"max_completion_tokens": 500, "_reasoning": True, "_thinking_budget": 2048})
        self.assertGreater(payload["max_tokens"], payload["thinking"]["budget_tokens"])
        self.assertNotIn("max_completion_tokens", payload)
        self.assertEqual(payload["thinking"]["budget_tokens"], 2048)

    def test_custom_plugin_builds_safe_plan(self):
        async def run():
            plan = await plugin_manager.plan("hello lily please", 1, 2, 3)
            self.assertIsNotNone(plan)
            self.assertEqual(plan.action, "plugin_reply")
        asyncio.run(run())

    def test_daily_quota_persists(self):
        async def run():
            with tempfile.TemporaryDirectory() as directory:
                database = Database(str(Path(directory) / "test.sqlite3"))
                await database.init()
                await database.update_chat_settings(1, {"daily_request_limit": 2, "monthly_request_limit": 10})
                self.assertEqual((await database.charge_request(7, 1))[0], True)
                self.assertEqual((await database.charge_request(7, 1))[0], True)
                self.assertEqual((await database.charge_request(7, 1))[0], False)
        asyncio.run(run())

    def test_group_control_catalogue_has_sixty_plus_controls(self):
        self.assertGreaterEqual(len(GROUP_CONTROLS), 60)
        self.assertIn("domain_blocklist", GROUP_CONTROL_MAP)
        self.assertIn("join_request_review", GROUP_CONTROL_MAP)
        self.assertIn("daily_digest", GROUP_CONTROL_MAP)

    def test_group_control_policy_and_moderation_records_persist(self):
        async def run():
            with tempfile.TemporaryDirectory() as directory:
                database = Database(str(Path(directory) / "controls.sqlite3"))
                await database.init()
                await database.set_control(1, "caps", True)
                self.assertTrue((await database.get_controls(1))["caps"])
                await database.set_trusted_member(1, 88, 7, True)
                self.assertTrue(await database.is_trusted_member(1, 88))
                await database.set_blocked_domain(1, "https://spam.example/path", 7, True)
                self.assertEqual(await database.list_blocked_domains(1), ["spam.example"])
                report_id = await database.create_report(1, 7, 88, "Repeated spam")
                self.assertEqual((await database.list_reports(1))[0]["id"], report_id)
                self.assertTrue(await database.resolve_report(1, report_id))
                case_note_id = await database.add_case_note(1, 7, "Escalate only if repeated", report_id, 88)
                self.assertEqual((await database.list_case_notes(1, report_id))[0]["id"], case_note_id)
                await database.record_member_join(1, 99, True)
                self.assertIsNotNone(await database.member_joined_at(1, 99))
                self.assertEqual((await database.list_pending_verifications(1))[0]["user_id"], 99)
                self.assertTrue(await database.complete_verification(1, 99))
                self.assertEqual(await database.list_pending_verifications(1), [])
        asyncio.run(run())

    def test_heuristic_router_configures_group_control(self):
        plan = AIClient().heuristic_plan("Lily, enable caps control", {"chat_type": "group", "reply": {}})
        self.assertEqual(plan.action, "configure_group_control")
        self.assertEqual(plan.args["control"], "caps")
        self.assertTrue(plan.args["enabled"])

    def test_heuristic_router_understands_expanded_rose_actions(self):
        client = AIClient()
        warning = client.heuristic_plan("Lily warn user 123456789 for spam", {"chat_type": "group", "reply": {}})
        self.assertEqual(warning.action, "warn_user")
        restricted = client.heuristic_plan("Lily restrict user 123456789 to text only", {"chat_type": "group", "reply": {}})
        self.assertEqual(restricted.action, "restrict_user")
        welcome = client.heuristic_plan("Lily set welcome message to Read our rules, {user}", {"chat_type": "group", "reply": {}})
        self.assertEqual(welcome.action, "set_welcome")
        goodbye = client.heuristic_plan("Lily set goodbye message to Bye {user}", {"chat_type": "group", "reply": {}})
        self.assertEqual(goodbye.action, "set_goodbye")
        case_note = client.heuristic_plan("Lily add a case note for report 7 saying review next incident", {"chat_type": "group", "reply": {}})
        self.assertEqual(case_note.action, "add_case_note")

    def test_heuristic_router_understands_media_and_audit_tools(self):
        client = AIClient()
        media = client.heuristic_plan("Lily show file details for this video", {"chat_type": "group", "reply": {}})
        self.assertEqual(media.action, "media_info")
        audit = client.heuristic_plan("Lily export moderation history", {"chat_type": "group", "reply": {}})
        self.assertEqual(audit.action, "export_audit")
        self.assertTrue(audit.requires_confirmation)
        rename = client.heuristic_plan("Lily rename uploads using template {title} - {quality}.{ext}", {"chat_type": "group", "reply": {}})
        self.assertEqual(rename.action, "set_auto_rename")
        self.assertEqual(rename.args["template"], "{title} - {quality}.{ext}")

    def test_heuristic_router_understands_production_upgrade_actions(self):
        client = AIClient()
        poll = client.heuristic_plan("Lily create poll: Ship the update? | Yes | No", {"chat_type": "group", "reply": {}})
        self.assertEqual(poll.action, "create_poll")
        self.assertEqual(poll.args["options"], ["Yes", "No"])
        escalation = client.heuristic_plan("Lily set warning escalation to 4 for 2 hours", {"chat_type": "group", "reply": {}})
        self.assertEqual(escalation.action, "configure_warning_escalation")
        self.assertEqual(escalation.args["threshold"], 4)
        self.assertEqual(escalation.args["seconds"], 7200)
        diagnostics = client.heuristic_plan("Lily show group diagnostics", {"chat_type": "group", "reply": {}})
        self.assertEqual(diagnostics.action, "group_diagnostics")

    def test_complete_free_model_registry_is_present(self):
        self.assertEqual(len(CATALOG), 16)
        self.assertGreaterEqual(len(PRESETS), 17)
        self.assertIn("cohere", PRESETS)
        self.assertIn("cloudflare-workers-ai", PRESETS)
        self.assertIn("ollama-local", PRESETS)

    def test_requested_fallback_tier_order_is_enforced(self):
        from lily.config import Settings
        configured = replace(
            Settings(),
            ai_profiles_json="",
            ai_keys=("openai-key",),
            ai_bases=("https://api.openai.com/v1",),
            openai_api_key="",
            openai_api_base="",
            ai_presets=("ollama-local", "gemini", "groq"),
            fallback_order=("free", "gemini", "openai", "groq"),
        )
        with patch.dict("os.environ", {"GEMINI_API_KEY": "gemini-key", "GROQ_API_KEY": "groq-key", "OLLAMA_BASE_URL": "http://127.0.0.1:11434/v1"}, clear=False):
            names = [str(profile["name"]) for profile in configured.model_profiles()]
        self.assertEqual(names, ["preset-ollama-local", "preset-gemini", "provider-1", "preset-groq"])

    def test_high_load_fallback_simulation_rate_limits_errors_and_recovery(self):
        async def run():
            requests: Counter[str] = Counter()
            free_recovered = False

            async def handler(request: httpx.Request) -> httpx.Response:
                nonlocal free_recovered
                host = request.url.host or ""
                requests[host] += 1
                if host == "free.test":
                    if free_recovered:
                        return httpx.Response(200, json={"choices": [{"message": {"content": "free recovered"}}]}, request=request)
                    return httpx.Response(429, json={"error": "rate limited"}, request=request)
                if host == "gemini.test":
                    raise httpx.ReadTimeout("simulated timeout", request=request)
                if host == "openai.test":
                    return httpx.Response(200, content=b"{invalid-json", request=request)
                return httpx.Response(200, json={"choices": [{"message": {"content": "groq fallback"}}]}, request=request)

            profiles = [
                ModelProfile("free", "https://free.test/v1", "key", "free", priority=0, max_retries=0),
                ModelProfile("gemini", "https://gemini.test/v1", "key", "gemini", priority=1, max_retries=0),
                ModelProfile("openai", "https://openai.test/v1", "key", "gpt-test", priority=2, max_retries=0),
                ModelProfile("groq", "https://groq.test/v1", "key", "groq", priority=3, max_retries=0),
            ]
            router = ModelRouter(profiles, cooldown_base=0.02, cooldown_max=0.02, transport=httpx.MockTransport(handler))
            payload = {"messages": [{"role": "user", "content": "load test"}], "_timeout": 1}
            results = await asyncio.gather(*(router.chat(payload) for _ in range(32)))
            self.assertTrue(all(profile.name == "groq" for _, profile in results))
            self.assertEqual(requests["free.test"], 1)
            self.assertEqual(requests["gemini.test"], 1)
            self.assertEqual(requests["openai.test"], 1)
            self.assertEqual(requests["groq.test"], 32)
            await asyncio.sleep(0.03)
            free_recovered = True
            response, profile = await router.chat(payload)
            self.assertEqual(profile.name, "free")
            self.assertEqual(response["choices"][0]["message"]["content"], "free recovered")
            status = {item["name"]: item for item in await router.status()}
            self.assertEqual(status["free"]["in_flight"], 0)
            self.assertGreaterEqual(status["gemini"]["failures"], 1)
            self.assertGreaterEqual(status["openai"]["failures"], 1)

        asyncio.run(run())


if __name__ == "__main__":
    unittest.main()
