from __future__ import annotations

import asyncio
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

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

    def test_heuristic_router_understands_channel_post(self):
        plan = AIClient().heuristic_plan("make an anime episode announcement for Dragon Ball", {})
        self.assertEqual(plan.action, "start_channel_post")

    def test_heuristic_router_reads_numeric_target_from_plain_text(self):
        plan = AIClient().heuristic_plan("Lily, demote user 123456789", {"chat_type": "cli", "reply": {}})
        self.assertEqual(plan.action, "demote_user")
        self.assertEqual(plan.args["user_id"], 123456789)

    def test_signed_stream_link_resolves_lily_managed_file(self):
        updated_settings = replace(settings, stream_public_base_url="https://lily.example.test", stream_signing_secret="test-signing-secret")
        path = settings.work_dir / "stream_test.bin"
        with patch.object(web_media, "settings", updated_settings):
            settings.work_dir.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"lily")
            link = stream_links.create(path, 99)
            token = link.rsplit("/", 1)[-1]
            self.assertEqual(stream_links.resolve(token), path.resolve())
        path.unlink(missing_ok=True)

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


if __name__ == "__main__":
    unittest.main()
