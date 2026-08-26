from __future__ import annotations

import asyncio
import logging

from telegram import Update
from telegram.ext import Application, CommandHandler

from .config import settings
from .db import db
from .handlers import help_message, register_handlers, start
from .queue_manager import encoding_queue
from .web_media import stream_links


logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    level=getattr(logging, __import__("os").getenv("LILY_LOG_LEVEL", "INFO").upper(), logging.INFO),
)
logger = logging.getLogger("lily")


async def help_handler(update: Update, context) -> None:
    await help_message(update)


async def post_shutdown(application: Application) -> None:
    await encoding_queue.stop()
    task = application.bot_data.pop("stream_server_task", None)
    if task:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)


async def post_init(application: Application) -> None:
    await db.init()
    if settings.stream_public_base_url:
        try:
            import uvicorn
            config = uvicorn.Config(stream_links.app(), host=settings.stream_bind_host, port=settings.stream_port, log_level="warning")
            application.bot_data["stream_server_task"] = asyncio.create_task(uvicorn.Server(config).serve(), name="lily-stream-server")
        except Exception as exc:
            logger.warning("Streaming server disabled: %s", exc)
    me = await application.bot.get_me()
    logger.info("Lily started as @%s using %s", me.username, settings.bot_api_base)


def build_application() -> Application:
    if not settings.bot_token:
        raise RuntimeError("Set TELEGRAM_BOT_TOKEN before starting Lily.")
    settings.prepare()
    builder = Application.builder().token(settings.bot_token)
    if settings.use_local_bot_api:
        builder = builder.base_url(settings.bot_api_base).base_file_url(settings.bot_file_base).local_mode(True)
    application = builder.post_init(post_init).post_shutdown(post_shutdown).build()
    # Only onboarding/help remain as optional Telegram commands; all actual work is AI-first natural language.
    application.add_handler(CommandHandler("start", start), group=-1)
    application.add_handler(CommandHandler("help", help_handler), group=-1)
    register_handlers(application)
    return application


def main() -> None:
    application = build_application()
    logger.info("Starting Lily with long polling. Use a webhook in production if preferred.")
    application.run_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=False)


if __name__ == "__main__":
    main()
