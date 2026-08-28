from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import os
import tempfile
import time
import unittest
import zipfile
from collections import Counter
from dataclasses import replace
from pathlib import Path
from urllib.parse import urlencode
from unittest.mock import AsyncMock, patch

import httpx
from fastapi import FastAPI

from lily.agent import ACTIONS, AIClient, AgentTeamMemo, Plan
from lily.agent_team import merge_role_reviews, public_team_summary, redact_team_text, role_review_context, select_roles
from lily.main import public_error_message
from lily.cli import public_agent_report
from lily.rich import live_activity_blocks
from lily.sandbox import sandbox_status
from lily.code_workspace import CodeWorkspace
from lily.skill_engine import select_skill
from lily.service_supervisor import ManagedServiceSupervisor, ProcessResult, SupervisorError
from lily.agent_roles import assign_roles, catalog as agent_role_catalog, catalog_summary
from lily.miniapp_bridge import MiniAppAuthError, MiniAppUser, _is_administrator, _public_review_rows, _safe_event_rows, install_miniapp_routes, miniapp_owner_access, public_miniapp_plan, public_model_status, public_operational_status, validate_init_data
from lily.model_router import ModelProfile, ModelRouter
from lily.plugin_manager import plugin_manager
from lily.db import Database
from lily.postbot import ChannelPostService
from lily.pagination import PaginationManager
from lily.rich import confirmation_keyboard
from lily.tools import safe_filename
import lily.web_media as web_media
from lily.web_media import WebSearch, stream_links
from lily.config import Settings, settings
from lily.free_models import CATALOG, PRESETS, profiles_for_presets
from lily.group_controls import GROUP_CONTROLS, GROUP_CONTROL_MAP
from lily.bot_factory import BotFactoryError, EnvironmentWizard, ManagedBotFactory
from lily.execution_workflow import visible_stages
from lily.knowledge_library import catalog as knowledge_catalog, read_skill
from lily.mangadex import MangaDexClient, MangaDexError
from lily.messaging import split_for_telegram
from lily.handlers import execute_plan
from lily.media_generation import MediaGeneration, TTS_VOICES


class LilyCoreTests(unittest.TestCase):
    def test_safe_filename_blocks_paths(self):
        self.assertEqual(safe_filename("../../secret.txt"), "secret.txt")
        self.assertNotIn("/", safe_filename("a/b:c?.txt"))

    def test_public_failure_message_does_not_leak_error_details(self):
        message = public_error_message()
        self.assertIn("could not complete", message)
        self.assertNotIn("traceback", message.lower())
        self.assertNotIn("token", message.lower())

    def test_rich_confirmation_payload(self):
        payload = confirmation_keyboard("abc")
        self.assertEqual(payload["inline_keyboard"][0][0]["callback_data"], "confirm:abc:yes")
        self.assertEqual(payload["inline_keyboard"][0][0].get("style"), "primary")
        self.assertEqual(payload["inline_keyboard"][0][1].get("style"), "danger")

    def test_ubuntu_agent_report_is_non_executing_and_omits_plan_arguments(self):
        plan = Plan(intent="ban", summary="Remove a spammer", action="ban_user", risk="dangerous", requires_confirmation=True, args={"user_id": 12345}, missing=[])
        report = public_agent_report(plan)
        self.assertFalse(report["executes"])
        self.assertTrue(report["confirmation_required"])
        self.assertNotIn("args", report)
        self.assertIn("public_stages", report)

    def test_ubuntu_sandbox_status_is_redacted_and_bounded(self):
        report = sandbox_status()
        self.assertEqual(report["runtime"], "ubuntu-local")
        self.assertFalse(report["persistent_service"])
        self.assertFalse(report["arbitrary_shell_execution"])
        self.assertIn("search", report["terminal_options"])
        self.assertNotIn("api_key", json.dumps(report).lower().replace("api_key_configured", ""))

    def test_live_activity_blocks_contain_only_public_status(self):
        blocks = live_activity_blocks("Encode permitted file", ["Validate file", "Deliver result"], "Validating the selected file.")
        serialized = json.dumps(blocks)
        self.assertIn("Lily live activity", serialized)
        self.assertIn("Validating the selected file.", serialized)
        self.assertNotIn("chain-of-thought", serialized.lower())

    def test_configured_web_search_returns_bounded_deduplicated_results(self):
        class Response:
            def raise_for_status(self):
                return None

            def json(self):
                return {
                    "Heading": "Dragon Ball",
                    "AbstractURL": "https://example.test/dragon-ball",
                    "AbstractText": "Official summary",
                    "RelatedTopics": [
                        {"FirstURL": "https://example.test/dragon-ball", "Text": "Duplicate - ignored"},
                        {"FirstURL": "https://example.test/wiki", "Text": "Dragon Ball - fan reference"},
                        {"FirstURL": "https://example.test/news", "Text": "Dragon Ball news - current"},
                    ],
                }

        class Client:
            async def __aenter__(self):
                return self

            async def __aexit__(self, *_args):
                return None

            async def get(self, *_args, **_kwargs):
                return Response()

        async def run():
            with patch("lily.web_media.httpx.AsyncClient", return_value=Client()):
                results = await WebSearch().search("Dragon Ball", limit=2)
            self.assertEqual(len(results), 2)
            self.assertEqual(results[0]["url"], "https://example.test/dragon-ball")
            self.assertEqual(results[1]["url"], "https://example.test/wiki")

        asyncio.run(run())

    def test_code_workspace_isolated_write_validate_and_archive(self):
        with tempfile.TemporaryDirectory() as directory:
            workspace = CodeWorkspace(Path(directory) / "workspaces")
            created = workspace.create_project("user-42", "sample-code", "python", "A small demo")
            self.assertEqual(created["language"], "python")
            self.assertIn(".lily-project.json", [item["path"] for item in created["files"]])
            folder = workspace.mkdir("user-42", "sample-code", "src")
            self.assertEqual(folder["directory"], "src")
            written = workspace.write_file("user-42", "sample-code", "src/helper.py", "def hello():\n    return 'hi'\n")
            self.assertEqual(written["file"], "src/helper.py")
            validation = workspace.validate("user-42", "sample-code")
            self.assertFalse(validation["execution"])
            self.assertIn("main.py", validation["checked"])
            archive = workspace.archive("user-42", "sample-code")
            with zipfile.ZipFile(archive) as packaged:
                self.assertIn("main.py", packaged.namelist())
                self.assertIn("src/helper.py", packaged.namelist())
            with self.assertRaises(ValueError):
                workspace.write_file("user-42", "sample-code", "../outside.py", "no")

    def test_heuristic_code_creator_makes_safe_workspace_plan(self):
        plan = AIClient().heuristic_plan("Lily create a Python code project called hello-bot", {"chat_type": "private", "reply": {}})
        self.assertEqual(plan.action, "create_code_project")
        self.assertEqual(plan.args["language"], "python")
        self.assertEqual(plan.args["project"], "hello-bot")
        self.assertEqual(AIClient().heuristic_plan("show my code projects", {"reply": {}}).action, "code_project_status")
        cancellation = AIClient().heuristic_plan("cancel code project abcdef123456", {"reply": {}})
        self.assertEqual(cancellation.action, "cancel_code_project")
        self.assertTrue(cancellation.requires_confirmation)

    def test_text_to_speech_is_bounded_confirmed_and_voice_validated(self):
        plan = AIClient().heuristic_plan("Lily read aloud: Welcome to the community, voice Kore", {"chat_type": "private", "reply": {}})
        self.assertEqual(plan.action, "generate_speech")
        self.assertTrue(plan.requires_confirmation)
        self.assertEqual(plan.risk, "risky")
        self.assertEqual(plan.args["voice"], "Kore")
        self.assertEqual(assign_roles(plan).primary.slug, "media-engineer")
        unsafe = Plan.from_dict({"action": "generate_speech", "risk": "safe", "requires_confirmation": False, "args": {"text": "Hello"}})
        self.assertEqual(unsafe.risk, "risky")
        self.assertTrue(unsafe.requires_confirmation)

        async def run():
            service = MediaGeneration()
            configured = replace(settings, speech_generation_url="https://speech.example.test/v1", speech_generation_api_key="speech-test-key", speech_max_chars=100)
            with patch("lily.media_generation.settings", configured), patch.object(service, "_request", new=AsyncMock(return_value="https://speech.example.test/output.ogg")) as request:
                output = await service.speech("  Hello   Lily  ", "Kore", "en-US")
                self.assertEqual(output, "https://speech.example.test/output.ogg")
                request.assert_awaited_once_with("https://speech.example.test/v1", "speech-test-key", {"kind": "speech", "text": "Hello Lily", "voice": "Kore", "language_code": "en-US"})
                with self.assertRaises(ValueError):
                    await service.speech("Hello", "Unapproved voice")
        asyncio.run(run())
        self.assertIn("Kore", TTS_VOICES)

    def test_role_catalog_assigns_specialists_without_bypassing_safety(self):
        self.assertGreaterEqual(len(agent_role_catalog()), 200)
        self.assertGreaterEqual(len(agent_role_catalog("engineering")), 10)
        self.assertIn({"division": "engineering", "roles": len(agent_role_catalog("engineering"))}, catalog_summary())
        assignment = assign_roles(Plan(action="create_code_project", risk="safe"))
        self.assertEqual(assignment.primary.slug, "code-creator")
        self.assertIn("privacy-guardian", [role.slug for role in assignment.reviewers])
        moderation = assign_roles(Plan(action="ban_user", risk="dangerous", requires_confirmation=True))
        self.assertEqual(moderation.primary.slug, "community-moderator")
        self.assertIn("safety-reviewer", [role.slug for role in moderation.reviewers])
        self.assertTrue(AIClient().heuristic_plan("show agent roles", {"reply": {}}).action == "show_agent_roles")

    def test_agent_team_is_bounded_and_primary_role_stays_relevant(self):
        code_plan = Plan.from_dict({"action": "create_code_project", "risk": "safe", "args": {}, "missing": [], "summary": "Create a project"})
        roles = select_roles(code_plan, "Create a Python API project with tests and a database", 99)
        self.assertLessEqual(len(roles), 4)
        self.assertEqual(roles[0].slug, "code-creator")
        self.assertEqual(len({role.slug for role in roles}), len(roles))

    def test_agent_team_redacts_credentials_commands_and_private_reasoning(self):
        value = "token: super-secret-value\n$ curl https://example.invalid\nInternal analysis: step by step"
        safe = redact_team_text(value)
        self.assertNotIn("super-secret-value", safe)
        self.assertNotIn("curl https://", safe)
        self.assertNotIn("step by step", safe)
        context = role_review_context(value, Plan(action="web_search", summary="Find public results"))
        self.assertEqual(set(context), {"request", "central_plan"})
        self.assertNotIn("super-secret-value", json.dumps(context))

    def test_agent_team_merges_only_safety_constraints_not_role_authority(self):
        plan = Plan.from_dict({"intent": "ban_user", "summary": "Ban a member", "action": "ban_user", "risk": "safe", "requires_confirmation": False, "args": {"user_id": 12345}, "missing": [], "confidence": 0.9})
        memo = AgentTeamMemo("Safety Reviewer", "assurance", "token: hidden-value", "safe", False, ("Confirm the moderation target",))
        merged = merge_role_reviews(plan, [memo])
        self.assertEqual(merged.action, "ban_user")
        self.assertEqual(merged.args["user_id"], 12345)
        self.assertEqual(merged.risk, "dangerous")
        self.assertTrue(merged.requires_confirmation)
        self.assertIn("Confirm the moderation target", merged.missing)
        team = merged.args["_agent_team"]
        self.assertEqual(team["reviewed_count"], 1)
        self.assertNotIn("hidden-value", json.dumps(team))
        self.assertNotIn("args", team["members"][0])
        public = public_team_summary(merged)
        self.assertEqual(public["reviewed_count"], 1)
        self.assertNotIn("summary", json.dumps(public))
        self.assertNotIn("hidden-value", json.dumps(public))
        malformed = Plan(args={"_agent_team": {"mode": "llm-reviewed", "members": [], "reviewed_count": "not-a-number"}})
        self.assertEqual(public_team_summary(malformed)["reviewed_count"], 0)

    def test_agent_team_model_failure_preserves_primary_plan(self):
        class FailingTeamClient(AIClient):
            @property
            def providers(self):
                return [object()]

            async def plan(self, text, context, memories, chat_settings):
                return Plan.from_dict({"action": "web_search", "summary": "Search the web", "args": {"query": "Lily"}, "missing": []})

            async def _role_memo(self, role, text, plan):
                return None

        team_settings = replace(settings, enable_agent_team=True, agent_team_max_roles=3)
        with patch("lily.agent.settings", team_settings):
            result = asyncio.run(FailingTeamClient().team_plan("search Lily", {"reply": {}}, [], {}))
        self.assertEqual(result.action, "web_search")
        self.assertNotIn("_agent_team", result.args)

    def test_agent_team_live_review_path_is_bounded_redacted_and_safety_monotonic(self):
        class TeamClient(AIClient):
            def __init__(self):
                self.payloads = []

            @property
            def providers(self):
                return [object()]

            async def plan(self, text, context, memories, chat_settings):
                return Plan.from_dict({"action": "create_poll", "summary": "Create a poll", "risk": "risky", "requires_confirmation": True, "args": {"question": "Choose"}, "missing": []})

            async def _request(self, payload, requirement="chat"):
                self.payloads.append(payload)
                return {"choices": [{"message": {"content": json.dumps({"summary": "Reviewed safely", "risk": "safe", "requires_confirmation": False, "missing": []})}}]}

        team_settings = replace(settings, enable_agent_team=True, agent_team_max_roles=2)
        client = TeamClient()
        with patch("lily.agent.settings", team_settings):
            result = asyncio.run(client.team_plan("Create a poll. token: 1234567890", {"reply": {}}, [], {}))
        self.assertEqual(len(client.payloads), 2)
        self.assertEqual(result.action, "create_poll")
        self.assertEqual(result.risk, "risky")
        self.assertTrue(result.requires_confirmation)
        self.assertEqual(result.args["question"], "Choose")
        sent_to_roles = json.dumps(client.payloads)
        self.assertNotIn("1234567890", sent_to_roles)
        self.assertEqual(public_team_summary(result)["reviewed_count"], 2)

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

    def test_post_blocks_sanitize_untrusted_links_and_trim_fields(self):
        blocks = ChannelPostService().announcement_blocks({
            "title": "Dragon Ball " * 80,
            "type": "TV",
            "genres": "Action " * 100,
            "plot": "A safe synopsis.",
            "site_url": "javascript:alert('bad')",
            "anilist_id": 20,
        })
        title = blocks[0]["text"][0]["text"]
        buttons = next(block for block in blocks if block["type"] == "buttons")["buttons"]
        self.assertLessEqual(len(title), 180)
        self.assertEqual(buttons[0]["url"], "https://anilist.co/anime/20")
        self.assertEqual(buttons[1]["style"], "secondary")

    def test_post_lookup_normalizes_filenames_and_caches_metadata(self):
        class Response:
            def raise_for_status(self):
                return None

            def json(self):
                return {"data": {"Page": {"media": [{
                    "id": 20,
                    "title": {"english": "Dragon Ball", "romaji": None, "native": None},
                    "format": "TV",
                    "averageScore": 85,
                    "meanScore": None,
                    "status": "FINISHED",
                    "episodes": 153,
                    "genres": ["Action"],
                    "description": "A &amp; B",
                    "coverImage": {"large": "https://example.test/cover.jpg"},
                    "siteUrl": "https://anilist.co/anime/20/Dragon-Ball/",
                    "nextAiringEpisode": None,
                    "studios": {"nodes": []},
                }]}}}

        class Client:
            calls = 0

            async def __aenter__(self):
                return self

            async def __aexit__(self, *_args):
                return None

            async def post(self, *_args, **_kwargs):
                self.calls += 1
                return Response()

        async def run():
            client = Client()
            service = ChannelPostService()
            with patch("lily.postbot.httpx.AsyncClient", return_value=client):
                first = await service.lookup_anime("Dragon.Ball.S01E01.1080p.mkv")
                second = await service.lookup_anime("Dragon.Ball.S01E01.1080p.mkv")
            self.assertEqual(client.calls, 1)
            self.assertEqual(first["title"], "Dragon Ball")
            self.assertEqual(first["plot"], "A & B")
            self.assertEqual(second["site_url"], "https://anilist.co/anime/20/Dragon-Ball/")

        asyncio.run(run())

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

    def test_code_project_job_lifecycle_is_requester_scoped(self):
        async def run():
            with tempfile.TemporaryDirectory() as directory:
                database = Database(str(Path(directory) / "projects.sqlite3"))
                await database.init()
                job_id = await database.create_code_project_job(101, 7, "hello-bot", "python")
                self.assertTrue(await database.start_code_project_job(job_id))
                await database.update_code_project_job(job_id, "Packaging source archive")
                item = await database.get_code_project_job(job_id, 101, 7)
                self.assertEqual(item["state"], "running")
                self.assertEqual(item["stage"], "Packaging source archive")
                self.assertFalse(await database.request_code_project_cancel(job_id, 101, 8))
                self.assertTrue(await database.request_code_project_cancel(job_id, 101, 7))
                self.assertTrue(await database.code_project_cancelled(job_id))
                await database.finish_code_project_job(job_id, "cancelled", "Cancelled before delivery", file_count=3)
                final = await database.get_code_project_job(job_id, 101, 7)
                self.assertEqual(final["state"], "cancelled")
                self.assertEqual(final["file_count"], 3)
                self.assertEqual(len(await database.list_code_project_jobs(101, 7)), 1)
        asyncio.run(run())

    def test_miniapp_init_data_validation_and_requester_scoped_cancellation(self):
        token = "test-miniapp-token"
        values = {
            "auth_date": "1000",
            "query_id": "AAE",
            "user": json.dumps({"id": 77, "first_name": "Lily", "username": "lily_owner"}, separators=(",", ":")),
        }
        check_string = "\n".join(f"{key}={values[key]}" for key in sorted(values))
        secret = hmac.new(b"WebAppData", token.encode("utf-8"), hashlib.sha256).digest()
        init_data = urlencode({**values, "hash": hmac.new(secret, check_string.encode("utf-8"), hashlib.sha256).hexdigest()})
        user = validate_init_data(init_data, token, max_age_seconds=300, now=1050)
        self.assertEqual(user.id, 77)
        self.assertEqual(user.public_dict()["username"], "lily_owner")
        with self.assertRaises(MiniAppAuthError):
            validate_init_data(init_data.replace("AAE", "BAD"), token, max_age_seconds=300, now=1050)
        with self.assertRaises(MiniAppAuthError):
            validate_init_data(init_data, token, max_age_seconds=60, now=1200)

        async def run():
            with tempfile.TemporaryDirectory() as directory:
                database = Database(str(Path(directory) / "miniapp.sqlite3"))
                await database.init()
                job_id = await database.create_code_project_job(101, 77, "bridge-project", "python")
                self.assertTrue(await database.request_code_project_cancel_for_user(job_id, 77))
                self.assertFalse(await database.request_code_project_cancel_for_user(job_id, 78))
                job = await database.get_code_project_job(job_id, 101, 77)
                self.assertEqual(job["state"], "cancelled")
        asyncio.run(run())

    def test_miniapp_public_ai_payload_omits_arguments_memos_and_provider_errors(self):
        plan = Plan.from_dict({
            "intent": "moderation",
            "summary": "Review a group moderation request",
            "action": "ban_user",
            "risk": "safe",
            "requires_confirmation": False,
            "args": {"user_id": 123456, "token": "must-not-appear", "_agent_team": {"mode": "llm-reviewed", "reviewed_count": 1, "members": [{"role": "Safety Reviewer", "division": "assurance", "summary": "private memo"}]}},
            "missing": [],
        })
        public = public_miniapp_plan(plan)
        serialized = json.dumps(public)
        self.assertEqual(public["risk"], "dangerous")
        self.assertTrue(public["requires_confirmation"])
        self.assertNotIn("user_id", serialized)
        self.assertNotIn("must-not-appear", serialized)
        self.assertNotIn("private memo", serialized)
        self.assertEqual(public["team"]["roles"], [{"role": "Safety Reviewer", "division": "assurance"}])
        models = public_model_status([{"name": "Free Router", "model": "small", "family": "openai", "privacy_tier": "private", "capabilities": ["chat"], "available": True, "api_key": "not-public", "last_error": "not-public"}])
        self.assertEqual(models, [{"name": "Free Router", "model": "small", "family": "openai", "privacy_tier": "private", "capabilities": ["chat"], "available": True}])

    def test_miniapp_owner_and_admin_panel_routes_are_server_scoped(self):
        owner = MiniAppUser(77, "Lily", "lily_owner")
        stranger = MiniAppUser(78, "Other", "other")
        config = Settings(bot_token="test-token", enable_miniapp_bridge=True, admin_user_ids=(77,))
        self.assertTrue(miniapp_owner_access(owner, config))
        self.assertFalse(miniapp_owner_access(stranger, config))
        self.assertFalse(miniapp_owner_access(owner, Settings(bot_token="test-token", enable_miniapp_bridge=True, admin_user_ids=())))
        events = _safe_event_rows([{"event": "ban_user", "created_at": 123, "detail": {"user_id": 99, "reason": "private"}}])
        self.assertEqual(events, [{"event": "ban_user", "created_at": 123}])
        app = FastAPI()
        install_miniapp_routes(app, Database(":memory:"), config)
        paths = {route.path for route in app.routes}
        self.assertIn("/miniapp/v1/panel/owner", paths)
        self.assertIn("/miniapp/v1/panel/group", paths)

    def test_miniapp_operations_groups_and_review_payloads_are_bounded(self):
        config = Settings(bot_token="test-token", enable_miniapp_bridge=True, admin_user_ids=(77,))
        status = public_operational_status([{"available": True}, {"available": False}], config)
        self.assertEqual(status["api_bridge"], "enabled")
        self.assertEqual(status["available_model_count"], 1)
        self.assertFalse(_is_administrator({"status": "member"}))
        self.assertTrue(_is_administrator({"status": "administrator"}))
        reviews = _public_review_rows([{"id": 8, "status": "open", "created_at": 123, "target_user_id": 456, "reporter_id": 789, "reason": "private detail"}])
        payload = json.dumps(reviews)
        self.assertEqual(reviews, [{"id": 8, "status": "open", "created_at": 123, "target_present": True}])
        self.assertNotIn("private detail", payload)
        self.assertNotIn("456", payload)
        self.assertNotIn("789", payload)

        async def run() -> None:
            with tempfile.TemporaryDirectory() as directory:
                database = Database(str(Path(directory) / "selector.sqlite3"))
                await database.init()
                async with database.connect() as connection:
                    await connection.execute("INSERT INTO chats(chat_id,title,settings_json,created_at,updated_at) VALUES(?,?,?,?,?)", (-1009, "Trusted group", "{}", 1, 5))
                    await connection.execute("INSERT INTO chats(chat_id,title,settings_json,created_at,updated_at) VALUES(?,?,?,?,?)", (77, "Private", "{}", 1, 10))
                    await connection.commit()
                self.assertEqual(await database.list_known_group_chats(), [{"chat_id": -1009, "title": "Trusted group", "updated_at": 5}])
        asyncio.run(run())

    def test_miniapp_panel_endpoints_require_signed_configured_owner_and_live_group_admin(self):
        token = "panel-test-token"
        def signed_init_data(user_id: int) -> str:
            values = {"auth_date": str(int(time.time())), "query_id": "PANEL", "user": json.dumps({"id": user_id, "first_name": "Lily"}, separators=(",", ":"))}
            check_string = "\n".join(f"{key}={values[key]}" for key in sorted(values))
            secret = hmac.new(b"WebAppData", token.encode("utf-8"), hashlib.sha256).digest()
            return urlencode({**values, "hash": hmac.new(secret, check_string.encode("utf-8"), hashlib.sha256).hexdigest()})

        async def run():
            with tempfile.TemporaryDirectory() as directory:
                database = Database(str(Path(directory) / "panel.sqlite3"))
                await database.init()
                await database.get_chat_settings(-100_123, "Verified crew")
                await database.audit(-100_123, 77, "configure_group_control", {"secret": "not public"})
                report_id = await database.create_report(-100_123, 501, 502, "private moderator report")
                app = FastAPI()
                config = Settings(bot_token=token, enable_miniapp_bridge=True, miniapp_init_data_ttl_seconds=86_400, admin_user_ids=(77,))
                install_miniapp_routes(app, database, config)

                async def administrator_call(method, payload):
                    self.assertEqual(method, "getChatMember")
                    self.assertEqual(payload["chat_id"], -100_123)
                    return {"status": "administrator" if payload["user_id"] == 77 else "member"}

                transport = httpx.ASGITransport(app=app)
                async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                    headers = {"X-Telegram-Init-Data": signed_init_data(77)}
                    non_admin_headers = {"X-Telegram-Init-Data": signed_init_data(78)}
                    with patch("lily.miniapp_bridge.rich.call", new=AsyncMock(side_effect=administrator_call)):
                        owner = await client.get("/miniapp/v1/panel/owner", headers=headers)
                        group = await client.get("/miniapp/v1/panel/group", params={"chat_id": -100_123}, headers=headers)
                        operations = await client.get("/miniapp/v1/operations/status", headers=headers)
                        groups = await client.get("/miniapp/v1/groups", headers=headers)
                        reviews = await client.get("/miniapp/v1/panel/reviews", params={"chat_id": -100_123}, headers=headers)
                        other_groups = await client.get("/miniapp/v1/groups", headers=non_admin_headers)
                        denied_reviews = await client.get("/miniapp/v1/panel/reviews", params={"chat_id": -100_123}, headers=non_admin_headers)
                    self.assertEqual(owner.status_code, 200)
                    self.assertEqual(owner.json()["aggregates"]["audit_log"], 1)
                    self.assertNotIn("secret", json.dumps(owner.json()))
                    self.assertEqual(group.status_code, 200)
                    self.assertEqual(group.json()["role"], "group_admin")
                    self.assertEqual(group.json()["recent_activity"], [{"event": "configure_group_control", "created_at": group.json()["recent_activity"][0]["created_at"]}])
                    self.assertNotIn("secret", json.dumps(group.json()))
                    self.assertEqual(operations.status_code, 200)
                    self.assertEqual(operations.json()["api_bridge"], "enabled")
                    self.assertNotIn("provider", json.dumps(operations.json()).lower())
                    self.assertNotIn("error", json.dumps(operations.json()).lower())
                    self.assertEqual(groups.json()["groups"], [{"chat_id": -100_123, "title": "Verified crew", "updated_at": groups.json()["groups"][0]["updated_at"]}])
                    self.assertEqual(other_groups.status_code, 200)
                    self.assertEqual(other_groups.json()["groups"], [])
                    self.assertEqual(reviews.status_code, 200)
                    self.assertEqual(reviews.json()["reviews"], [{"id": report_id, "status": "open", "created_at": reviews.json()["reviews"][0]["created_at"], "target_present": True}])
                    review_payload = json.dumps(reviews.json())
                    self.assertNotIn("private moderator report", review_payload)
                    self.assertNotIn("501", review_payload)
                    self.assertNotIn("502", review_payload)
                    self.assertEqual(denied_reviews.status_code, 403)
        asyncio.run(run())

    def test_managed_service_supervisor_is_allowlisted_owned_and_redacted(self):
        async def run():
            with tempfile.TemporaryDirectory() as directory:
                database = Database(str(Path(directory) / "supervisor.sqlite3"))
                await database.init()
                await database.register_managed_project({
                    "slug": "demo-bot", "repository_url": "https://github.com/example/demo-bot", "runtime": "python",
                    "run_profile": "python-main", "run_target": "main.py", "project_root": "/srv/lily/projects/demo-bot",
                    "env_path": "/etc/lily/projects/demo-bot.env", "owner_id": 7, "state": "registered",
                })
                calls: list[list[str]] = []

                async def runner(command: list[str]) -> ProcessResult:
                    calls.append(command)
                    if command[0] == "journalctl":
                        return ProcessResult(0, "API_KEY=not-for-users\nAuthorization: Bearer secret-value\nnormal line", "")
                    return ProcessResult(0, "active\nrunning\nloaded", "")

                disabled = ManagedServiceSupervisor(database, replace(settings, enable_managed_service_supervisor=False, allowed_managed_service_slugs=("demo-bot",)), runner)
                report = await disabled.status("demo-bot", 7)
                self.assertFalse(report["enabled"])
                self.assertEqual(calls, [])
                enabled = ManagedServiceSupervisor(database, replace(settings, enable_managed_service_supervisor=True, allowed_managed_service_slugs=("demo-bot",)), runner)
                self.assertEqual((await enabled.status("demo-bot", 7))["state"], "available")
                self.assertEqual(calls[-1][:3], ["systemctl", "--user", "show"])
                await enabled.control("demo-bot", 7, "restart")
                self.assertEqual(calls[-1], ["systemctl", "--user", "restart", "lily-managed-demo-bot.service"])
                logs = await enabled.logs("demo-bot", 7)
                self.assertIn("[REDACTED]", logs["lines"])
                self.assertNotIn("secret-value", logs["lines"])
                with self.assertRaises(SupervisorError):
                    await enabled.status("demo-bot", 8)
        asyncio.run(run())

    def test_automatic_skill_selection_preserves_approvals_and_cooldowns(self):
        safe_skill = {
            "id": "safe-skill", "name": "Greeting", "enabled": 1, "priority": 20,
            "trigger": {"keywords": ["hello"]}, "action": {"action": "plugin_reply", "args": {"text": "Welcome"}},
            "confirmation": "never", "execution_mode": "auto", "cooldown_seconds": 0, "created_at": 1,
        }
        matched = select_skill([safe_skill], "well, hello Lily", now=100)
        self.assertEqual(matched.state, "automatic")
        self.assertFalse(matched.plan.requires_confirmation)
        self.assertEqual(matched.plan.action, "plugin_reply")

        dangerous_skill = {
            "id": "danger-skill", "name": "Unsafe ban", "enabled": 1, "priority": 50,
            "trigger": {"contains": ["ban now"]}, "action": {"action": "ban_user", "args": {"user_id": 7}},
            "confirmation": "never", "execution_mode": "auto", "cooldown_seconds": 0, "created_at": 2,
        }
        protected = select_skill([dangerous_skill], "please ban now", now=100)
        self.assertEqual(protected.state, "approval_required")
        self.assertTrue(protected.plan.requires_confirmation)
        self.assertEqual(protected.plan.risk, "dangerous")

        cooled = {**safe_skill, "last_run_at": 95, "cooldown_seconds": 30}
        delayed = select_skill([cooled], "hello", now=100)
        self.assertEqual(delayed.state, "cooldown")
        self.assertEqual(delayed.cooldown_remaining, 25)

    def test_skill_run_database_claim_history_and_priority(self):
        async def run():
            with tempfile.TemporaryDirectory() as directory:
                database = Database(str(Path(directory) / "skills.sqlite3"))
                await database.init()
                low = await database.save_skill(1, 7, "Low", {"contains": ["hello"]}, {"action": "plugin_reply", "text": "low"}, confirmation="never", priority=10, execution_mode="auto")
                high = await database.save_skill(1, 7, "High", {"contains": ["hello"]}, {"action": "plugin_reply", "text": "high"}, confirmation="never", cooldown_seconds=60, priority=500, execution_mode="auto")
                bounded = await database.save_skill(1, 7, "Bounded", {"contains": ["later"]}, {"action": "plugin_reply", "text": "later"}, cooldown_seconds="not-a-number", priority="not-a-number", execution_mode="invalid")
                skills = await database.list_skills(1)
                self.assertEqual(skills[0]["id"], high)
                self.assertEqual(next(item for item in skills if item["id"] == bounded)["cooldown_seconds"], 0)
                self.assertEqual(next(item for item in skills if item["id"] == bounded)["priority"], 100)
                self.assertEqual(next(item for item in skills if item["id"] == bounded)["execution_mode"], "suggest")
                self.assertTrue(await database.claim_skill_run(high, 60, now=1_000))
                self.assertFalse(await database.claim_skill_run(high, 60, now=1_030))
                self.assertTrue(await database.claim_skill_run(high, 60, now=1_060))
                run_id = await database.create_skill_run(high, 1, 7, "plugin_reply", "running", "High")
                await database.finish_skill_run(run_id, "completed", "Completed")
                history = await database.list_skill_runs(1, 7)
                self.assertEqual(history[0]["state"], "completed")
                self.assertEqual(history[0]["detail"], "Completed")
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
        self.assertGreaterEqual(len(GROUP_CONTROLS), 64)
        self.assertIn("domain_blocklist", GROUP_CONTROL_MAP)
        self.assertIn("join_request_review", GROUP_CONTROL_MAP)
        self.assertIn("daily_digest", GROUP_CONTROL_MAP)
        self.assertIn("default_member_permissions", GROUP_CONTROL_MAP)
        self.assertIn("invite_link_management", GROUP_CONTROL_MAP)
        self.assertIn("forum_topic_management", GROUP_CONTROL_MAP)

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

    def test_heuristic_router_understands_new_bounded_group_management_skills(self):
        client = AIClient()
        read_only = client.heuristic_plan("Lily lock this group", {"chat_type": "group", "reply": {}})
        self.assertEqual(read_only.action, "set_group_default_permissions")
        self.assertEqual(read_only.args["mode"], "read_only")
        self.assertTrue(read_only.requires_confirmation)
        restore = client.heuristic_plan("Lily unlock this group", {"chat_type": "group", "reply": {}})
        self.assertEqual(restore.action, "set_group_default_permissions")
        self.assertEqual(restore.args["mode"], "normal")
        invite = client.heuristic_plan("Lily create invite link named weekend for 20 members expires 24 hours", {"chat_type": "group", "reply": {}})
        self.assertEqual(invite.action, "create_invite_link")
        self.assertTrue(invite.requires_confirmation)
        revoke = client.heuristic_plan("Lily revoke invite link https://t.me/+exampleInvite", {"chat_type": "group", "reply": {}})
        self.assertEqual(revoke.action, "revoke_invite_link")
        self.assertTrue(revoke.requires_confirmation)
        topic = client.heuristic_plan("Lily create forum topic called Releases", {"chat_type": "supergroup", "reply": {}})
        self.assertEqual(topic.action, "create_forum_topic")
        self.assertEqual(topic.args["name"], "Releases")
        self.assertTrue(topic.requires_confirmation)
        close = client.heuristic_plan("Lily close this topic", {"chat_type": "supergroup", "message_thread_id": 42, "reply": {}})
        self.assertEqual(close.action, "close_forum_topic")
        self.assertEqual(close.args["message_thread_id"], 42)
        self.assertTrue(close.requires_confirmation)
        roster = client.heuristic_plan("Lily show admins", {"chat_type": "group", "reply": {}})
        self.assertEqual(roster.action, "list_administrators")
        count = client.heuristic_plan("Lily how many members are here", {"chat_type": "group", "reply": {}})
        self.assertEqual(count.action, "group_member_count")
        self.assertEqual(assign_roles(topic).primary.slug, "community-moderator")

    def test_new_group_management_actions_cannot_lower_confirmation_or_scope_requirements(self):
        unsafe = Plan.from_dict({"action": "delete_forum_topic", "risk": "safe", "requires_confirmation": False, "args": {}, "missing": []})
        self.assertEqual(unsafe.risk, "dangerous")
        self.assertTrue(unsafe.requires_confirmation)
        self.assertIn("message thread ID", unsafe.missing[0])
        revoke = Plan.from_dict({"action": "revoke_invite_link", "risk": "safe", "requires_confirmation": False, "args": {}, "missing": []})
        self.assertTrue(revoke.requires_confirmation)
        self.assertIn("invite link", revoke.missing[0])

    def test_additional_group_tools_are_bounded_confirmed_and_role_routed(self):
        client = AIClient()
        announcement = client.heuristic_plan("Lily group announcement: The server maintenance starts at 8 PM.", {"chat_type": "group", "reply": {}})
        self.assertEqual(announcement.action, "send_group_announcement")
        self.assertTrue(announcement.requires_confirmation)
        self.assertEqual(announcement.args["text"], "The server maintenance starts at 8 PM.")
        checklist = client.heuristic_plan("Lily create checklist: Release tasks | Run tests | Review logs", {"chat_type": "group", "reply": {}})
        self.assertEqual(checklist.action, "post_checklist")
        self.assertEqual(checklist.args["items"], ["Run tests", "Review logs"])
        pins = client.heuristic_plan("Lily clear all pins", {"chat_type": "group", "reply": {}})
        self.assertEqual(pins.action, "unpin_all_messages")
        self.assertEqual(pins.risk, "dangerous")
        sticker = client.heuristic_plan("Lily set group sticker set to team_stickers", {"chat_type": "group", "reply": {}})
        self.assertEqual(sticker.action, "set_chat_sticker_set")
        self.assertEqual(sticker.args["sticker_set"], "team_stickers")
        invalid_sticker = Plan.from_dict({"action": "set_chat_sticker_set", "risk": "safe", "requires_confirmation": False, "args": {"sticker_set": "spaces are invalid"}})
        self.assertEqual(invalid_sticker.risk, "dangerous")
        self.assertTrue(invalid_sticker.requires_confirmation)
        self.assertTrue(invalid_sticker.missing)
        self.assertEqual(assign_roles(checklist).primary.slug, "community-moderator")

    def test_custom_command_aliases_preserve_safety_and_unambiguous_routing(self):
        client = AIClient()
        self.assertEqual(client.heuristic_plan("/help", {"chat_type": "private", "reply": {}}).action, "help")
        self.assertEqual(client.heuristic_plan("/models", {"chat_type": "private", "reply": {}}).action, "model_status")
        self.assertEqual(client.heuristic_plan("/id", {"chat_type": "group", "reply": {}}).action, "show_identifiers")
        group_lock = client.heuristic_plan("/lockgroup", {"chat_type": "group", "reply": {}})
        self.assertEqual(group_lock.action, "set_group_default_permissions")
        self.assertEqual(group_lock.args["mode"], "read_only")
        self.assertTrue(group_lock.requires_confirmation)
        announcement = client.heuristic_plan("/announce Maintenance begins at 8 PM", {"chat_type": "group", "reply": {}})
        self.assertEqual(announcement.action, "send_group_announcement")
        self.assertTrue(announcement.requires_confirmation)
        self.assertEqual(announcement.args["text"], "Maintenance begins at 8 PM")
        checklist = client.heuristic_plan("/checklist Release | Test | Review", {"chat_type": "group", "reply": {}})
        self.assertEqual(checklist.action, "post_checklist")
        self.assertEqual(checklist.args["items"], ["Test", "Review"])
        unmute = client.heuristic_plan("Lily unsilence user 123456789", {"chat_type": "group", "reply": {}})
        self.assertEqual(unmute.action, "unmute_user")
        self.assertTrue(unmute.requires_confirmation)
        timed_mute = client.heuristic_plan("Lily timeout user 123456789 for 15m", {"chat_type": "group", "reply": {}})
        self.assertEqual(timed_mute.action, "mute_user")
        self.assertEqual(timed_mute.args["seconds"], 900)
        unlocked = client.heuristic_plan("Lily unlock links", {"chat_type": "group", "reply": {}})
        self.assertEqual(unlocked.action, "set_lock")
        self.assertFalse(unlocked.args["enabled"])

    def test_new_group_management_executor_uses_fixed_api_methods_and_audits(self):
        class Chat:
            id = 100
            title = "Test group"
            type = "supergroup"

        class User:
            id = 200
            full_name = "Test admin"

        class Message:
            message_id = 300

        class UpdateStub:
            effective_chat = Chat()
            effective_user = User()
            effective_message = Message()

        class ContextStub:
            pass

        async def run():
            with tempfile.TemporaryDirectory() as directory:
                database = Database(str(Path(directory) / "group-actions.sqlite3"))
                await database.init()
                api_calls = []

                async def fixed_call(method, payload):
                    api_calls.append((method, payload))
                    if method == "createChatInviteLink":
                        return {"invite_link": "https://t.me/+ExampleInvite"}
                    return True

                with patch("lily.handlers.db", database), patch("lily.handlers.rich.call", new=AsyncMock(side_effect=fixed_call)), patch("lily.handlers.rich.send", new=AsyncMock(return_value={})) as send:
                    locked = await execute_plan(UpdateStub(), ContextStub(), Plan(action="set_group_default_permissions", args={"mode": "read_only"}))
                    invite = await execute_plan(UpdateStub(), ContextStub(), Plan(action="create_invite_link", args={"name": "weekend", "member_limit": 20, "expire_hours": 24}))
                    closed = await execute_plan(UpdateStub(), ContextStub(), Plan(action="close_forum_topic", args={"message_thread_id": 42}))
                    unpinned = await execute_plan(UpdateStub(), ContextStub(), Plan(action="unpin_all_messages"))
                    announcement = await execute_plan(UpdateStub(), ContextStub(), Plan(action="send_group_announcement", args={"text": "Maintenance at 8 PM."}))
                    checklist = await execute_plan(UpdateStub(), ContextStub(), Plan(action="post_checklist", args={"title": "Release", "items": ["Run tests", "Review logs"]}))
                    stickers = await execute_plan(UpdateStub(), ContextStub(), Plan(action="set_chat_sticker_set", args={"sticker_set": "team_stickers"}))
                    removed_stickers = await execute_plan(UpdateStub(), ContextStub(), Plan(action="delete_chat_sticker_set"))
                    invalid_mode = await execute_plan(UpdateStub(), ContextStub(), Plan(action="set_group_default_permissions", args={"mode": "unrestricted"}))
                    invalid_topic = await execute_plan(UpdateStub(), ContextStub(), Plan(action="close_forum_topic", args={"message_thread_id": "invalid"}))
                    with self.assertRaises(ValueError):
                        await execute_plan(UpdateStub(), ContextStub(), Plan(action="create_invite_link", args={"member_limit": "invalid"}))
                self.assertEqual(locked, "Regular members are now read-only.")
                self.assertIn("https://t.me/+ExampleInvite", invite)
                self.assertEqual(closed, "The forum topic was closed.")
                self.assertEqual(unpinned, "All pinned messages were removed from this group.")
                self.assertEqual(announcement, "The group announcement was posted.")
                self.assertEqual(checklist, "Posted the checklist with 2 item(s).")
                self.assertEqual(stickers, "The group sticker set was updated.")
                self.assertEqual(removed_stickers, "The group sticker set was removed.")
                self.assertIn("normal or read-only", invalid_mode)
                self.assertIn("valid numeric", invalid_topic)
                self.assertEqual([call[0] for call in api_calls], ["setChatPermissions", "createChatInviteLink", "closeForumTopic", "unpinAllChatMessages", "setChatStickerSet", "deleteChatStickerSet"])
                self.assertTrue(api_calls[0][1]["permissions"]["can_send_messages"] is False)
                self.assertEqual(api_calls[1][1]["member_limit"], 20)
                self.assertEqual(api_calls[2][1]["message_thread_id"], 42)
                self.assertEqual(api_calls[4][1]["sticker_set_name"], "team_stickers")
                self.assertEqual(send.await_count, 2)
                controls = await database.get_controls(100)
                self.assertTrue(controls["default_member_permissions"])
                self.assertTrue(controls["invite_link_management"])
                self.assertTrue(controls["forum_topic_management"])
                events = await database.recent_audit(100, limit=10)
                self.assertEqual({item["event"] for item in events}, {"set_group_default_permissions", "create_invite_link", "close_forum_topic", "unpin_all_messages", "send_group_announcement", "post_checklist", "set_chat_sticker_set", "delete_chat_sticker_set"})

        asyncio.run(run())

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

    def test_hardened_plan_enforces_confirmation_and_real_rose_mira_actions(self):
        unsafe = Plan.from_dict({"action": "ban_user", "risk": "safe", "requires_confirmation": False, "args": {}, "missing": []})
        self.assertEqual(unsafe.risk, "dangerous")
        self.assertTrue(unsafe.requires_confirmation)
        self.assertTrue(unsafe.missing)
        title = AIClient().heuristic_plan("Lily set group title to Dragon Ball Club", {"reply": {}})
        self.assertEqual(title.action, "set_chat_title")
        self.assertTrue(title.requires_confirmation)
        profile = AIClient().heuristic_plan("Lily show member profile 123456789", {"reply": {}})
        self.assertEqual(profile.action, "member_profile")
        explanation = AIClient().heuristic_plan("Lily explain this message", {"reply": {"text": "Hello world"}})
        self.assertEqual(explanation.action, "explain_message")
        self.assertEqual(explanation.args["message_text"], "Hello world")
        self.assertNotIn("summarize_chat", ACTIONS)
        self.assertNotIn("set_reminder", ACTIONS)

    def test_long_delivery_splits_below_bot_api_limit_at_readable_boundaries(self):
        text = ("One complete sentence for Lily. " * 250) + "Final part."
        chunks = split_for_telegram(text, 3500)
        self.assertGreater(len(chunks), 1)
        self.assertTrue(all(len(chunk) <= 3500 for chunk in chunks))
        self.assertEqual(" ".join(chunks).replace("  ", " ").strip(), text.strip())

    def test_complete_free_model_registry_is_present(self):
        self.assertEqual(len(CATALOG), 16)
        self.assertGreaterEqual(len(PRESETS), 17)
        self.assertIn("cohere", PRESETS)
        self.assertIn("cloudflare-workers-ai", PRESETS)
        self.assertEqual(PRESETS["huggingface"]["provider"], "Hugging Face")
        self.assertIn(PRESETS["huggingface"]["provider"], CATALOG)
        self.assertIn("ollama-local", PRESETS)

    def test_huggingface_preset_resolves_catalog_endpoint(self):
        with patch.dict("os.environ", {"HF_TOKEN": "test-token"}, clear=False):
            profiles = profiles_for_presets(("huggingface",), include_all_models=False, allow_public=False)
        self.assertEqual(len(profiles), 1)
        self.assertEqual(profiles[0]["base_url"], "https://router.huggingface.co/v1")
        self.assertEqual(profiles[0]["model"], "meta-llama/Llama-3.1-8B-Instruct")

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

    def test_environment_wizard_writes_redacted_mode_600_dotenv(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            example = root / ".env.example"
            example.write_text("# Bot token\nTELEGRAM_BOT_TOKEN=\nPUBLIC_URL=https://bot.example.test\nDEBUG=false\n", encoding="utf-8")
            wizard = EnvironmentWizard()
            schema = wizard.parse_example(example)
            supplied = {"TELEGRAM_BOT_TOKEN": "123:secret-value", "PUBLIC_URL": "https://bot.example.test", "DEBUG": "false"}
            self.assertEqual([item.name for item in schema], ["TELEGRAM_BOT_TOKEN", "PUBLIC_URL", "DEBUG"])
            self.assertTrue(schema[0].secret)
            self.assertNotIn("secret-value", str(wizard.redacted_status(schema, supplied)))
            destination = root / "bot.env"
            wizard.write(destination, schema, supplied)
            self.assertIn('TELEGRAM_BOT_TOKEN="123:secret-value"', destination.read_text(encoding="utf-8"))
            self.assertEqual(os.stat(destination).st_mode & 0o777, 0o600)
            with self.assertRaises(BotFactoryError):
                wizard.render(schema, {"UNKNOWN": "value"})

    def test_managed_bot_factory_validates_drafts_and_registry(self):
        async def run():
            with tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                configured = replace(settings, projects_root=root / "projects", project_env_root=root / "env", allowed_project_repositories=("https://github.com/example/manga-bot",), bot_factory_dry_run=True)
                database = Database(str(root / "registry.sqlite3"))
                await database.init()
                factory = ManagedBotFactory(database, configured)
                draft = factory.draft("manga-bot", "https://github.com/example/manga-bot", "python", "python-main", "bot.py")
                plan = await factory.clone_and_install(draft)
                self.assertTrue(plan["dry_run"])
                self.assertEqual(plan["run"], [str(root / "projects" / "manga-bot" / ".venv" / "bin" / "python"), "bot.py"])
                record = await factory.register_draft(draft, 42)
                self.assertEqual(record["slug"], "manga-bot")
                await database.save_project_env_schema("manga-bot", [{"name": "TELEGRAM_BOT_TOKEN", "required": True, "secret": True, "validation": "text"}])
                self.assertEqual((await database.get_project_env_schema("manga-bot"))[0]["name"], "TELEGRAM_BOT_TOKEN")
                with self.assertRaises(BotFactoryError):
                    factory.draft("../bad", "https://github.com/example/manga-bot", "python", "python-main", "bot.py")
                with self.assertRaises(BotFactoryError):
                    factory.draft("other-bot", "https://github.com/not-approved/bot", "python", "python-main", "bot.py")
        asyncio.run(run())

    def test_heuristic_router_understands_managed_bot_actions(self):
        client = AIClient()
        register = client.heuristic_plan(
            "Lily register bot manga-bot from https://github.com/example/manga-bot with python-main entrypoint bot.py",
            {"chat_type": "private", "reply": {}},
        )
        self.assertEqual(register.action, "register_managed_project")
        self.assertEqual(register.args["slug"], "manga-bot")
        self.assertEqual(register.args["run_profile"], "python-main")
        self.assertEqual(register.args["run_target"], "bot.py")
        provision = client.heuristic_plan("Lily provision bot manga-bot", {"chat_type": "private", "reply": {}})
        self.assertEqual(provision.action, "provision_managed_project")
        self.assertEqual(provision.args["slug"], "manga-bot")
        options = client.heuristic_plan("Lily show custom run command options", {"chat_type": "private", "reply": {}})
        self.assertEqual(options.action, "project_run_profiles")

    def test_manual_series_tracker_persists_and_parses(self):
        client = AIClient()
        track = client.heuristic_plan("Lily track manhwa Solo Leveling at chapter 210", {"chat_type": "group", "reply": {}})
        self.assertEqual(track.action, "track_series")
        self.assertEqual(track.args["title"], "Solo Leveling")
        self.assertEqual(track.args["last_chapter"], "210")
        async def run():
            with tempfile.TemporaryDirectory() as directory:
                database = Database(str(Path(directory) / "series.sqlite3"))
                await database.init()
                item = await database.track_series(1, "Solo Leveling", "manhwa", 7, "210")
                self.assertEqual(item["last_chapter"], "210")
                changed = await database.update_tracked_series(1, "solo leveling", "211", 7)
                self.assertEqual(changed["last_chapter"], "211")
                self.assertEqual((await database.list_tracked_series(1))[0]["title"], "Solo Leveling")
        asyncio.run(run())

    def test_chapter_download_requires_explicit_rights_and_source_details(self):
        client = AIClient()
        plan = client.heuristic_plan("Lily download 367 Dragon Ball chapter https://official.example/chapter-367.pdf", {"chat_type": "private", "reply": {}})
        self.assertEqual(plan.action, "download_chapter")
        self.assertEqual(plan.args["title"], "Dragon Ball")
        self.assertEqual(plan.args["chapter"], "367")
        self.assertFalse(plan.args["rights_confirmed"])
        self.assertIn("explicit distribution-rights confirmation", plan.missing)

    def test_encoding_queue_assigns_owner_bound_job_id_to_a_plan(self):
        async def run():
            class Message:
                message_id = 1
            class Chat:
                id = 8
            class User:
                id = 9
            class UpdateStub:
                effective_chat = Chat()
                effective_user = User()
                effective_message = Message()
            class ContextStub:
                user_data: dict[str, object] = {}
            with tempfile.TemporaryDirectory() as directory:
                database = Database(str(Path(directory) / "queue.sqlite3"))
                await database.init()
                from lily.queue_manager import EncodingQueue
                queue = EncodingQueue(database)
                plan = Plan(action="download_chapter", args={"title": "Licensed title"})
                async def worker(*_args):
                    return "done"
                job_id = await queue.enqueue(UpdateStub(), ContextStub(), plan, worker)
                self.assertEqual(plan.args["_queue_job_id"], job_id)
                self.assertEqual((await database.get_encoding_job(job_id))["state"], "queued")
                await queue.stop()
        asyncio.run(run())

    def test_managed_provisioning_requires_two_explicit_gates(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            configured = replace(settings, projects_root=root / "projects", project_env_root=root / "env", allowed_project_repositories=("https://github.com/example/manga-bot",), bot_factory_dry_run=False, enable_managed_project_provisioning=False)
            factory = ManagedBotFactory(Database(str(root / "registry.sqlite3")), configured)
            draft = factory.draft("manga-bot", "https://github.com/example/manga-bot", "python", "python-main", "bot.py")
            async def run():
                with self.assertRaises(BotFactoryError):
                    await factory.clone_and_install(draft)
            asyncio.run(run())
        status = AIClient().heuristic_plan("Lily show tool status", {"chat_type": "private", "reply": {}})
        self.assertEqual(status.action, "tool_capabilities")

    def test_visible_execution_stages_are_procedural_not_private_reasoning(self):
        stages = visible_stages("download_chapter", "dangerous", [], True)
        self.assertIn("Check source allow-lists, direct-file format, and declared rights", stages)
        self.assertIn("Wait for the requester’s explicit confirmation", stages)
        self.assertEqual(stages[-1], "Report a concise result")
        missing = visible_stages("ban_user", "dangerous", ["numeric user ID"], True)
        self.assertIn("Collect the missing details", missing)
        self.assertNotIn("Wait for the requester’s explicit confirmation", missing)

    def test_curated_operating_skill_catalogue_is_bounded_and_read_only(self):
        names = {item["name"] for item in knowledge_catalog()}
        self.assertTrue({"agent-workflow", "moderation", "media", "series-release", "queue", "bot-operations", "deployment"}.issubset(names))
        self.assertIn("never expose hidden chain-of-thought", read_skill("agent-workflow").lower())
        with self.assertRaises(KeyError):
            read_skill("../../etc/passwd")
        plan = AIClient().heuristic_plan("Lily show operating skills", {"chat_type": "private", "reply": {}})
        self.assertEqual(plan.action, "show_operating_skills")

    def test_mangadex_metadata_client_is_disabled_by_default_and_parses_metadata(self):
        async def run():
            disabled = MangaDexClient(replace(settings, enable_mangadex_metadata=False, mangadex_user_agent="Lily/1.0 (test@example.com)"))
            with self.assertRaises(MangaDexError):
                await disabled.search_titles("Frieren")
            await disabled.close()
            def handler(request):
                self.assertEqual(request.headers["User-Agent"], "Lily/1.0 (test@example.com)")
                return httpx.Response(200, json={"data": [{"id": "title-id", "attributes": {"title": {"en": "Frieren"}, "status": "ongoing", "year": 2020}}]})
            client = MangaDexClient(replace(settings, enable_mangadex_metadata=True, mangadex_user_agent="Lily/1.0 (test@example.com)", mangadex_min_interval_seconds=0.25), httpx.MockTransport(handler))
            results = await client.search_titles("Frieren")
            self.assertEqual(results[0]["title"], "Frieren")
            await client.close()
        asyncio.run(run())
        search = AIClient().heuristic_plan("Lily MangaDex search for Frieren", {"chat_type": "private", "reply": {}})
        self.assertEqual(search.action, "mangadex_search")


if __name__ == "__main__":
    unittest.main()
