from __future__ import annotations

import asyncio
import tempfile
import unittest
from pathlib import Path

from lily.agent import AIClient
from lily.model_router import ModelProfile, ModelRouter
from lily.plugin_manager import plugin_manager
from lily.db import Database
from lily.postbot import ChannelPostService
from lily.rich import confirmation_keyboard
from lily.tools import safe_filename


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
