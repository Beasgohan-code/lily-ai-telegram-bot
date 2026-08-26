from __future__ import annotations

import asyncio
import csv
import json
import re
import shutil
import subprocess
import time
import zipfile
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

import httpx
from telegram import ChatPermissions, InputFile, Update
from telegram.ext import ContextTypes

from .config import settings
from .db import Database


@dataclass
class ToolContext:
    update: Update
    context: ContextTypes.DEFAULT_TYPE
    db: Database
    progress: callable
    source_file: dict | None = None


def safe_filename(name: str, fallback: str = "lily_output") -> str:
    name = Path(name).name
    name = re.sub(r"[\x00-\x1f\x7f/\\:*?\"<>|]", "_", name).strip(" .")
    return name[:180] or fallback


def source_file_from_message(message):
    if not message:
        return None
    if message.document:
        return {"file_id": message.document.file_id, "file_name": message.document.file_name or "file.bin", "file_size": message.document.file_size or 0, "kind": "document"}
    if message.video:
        return {"file_id": message.video.file_id, "file_name": f"video_{message.video.file_unique_id}.mp4", "file_size": message.video.file_size or 0, "kind": "video"}
    if message.audio:
        return {"file_id": message.audio.file_id, "file_name": message.audio.file_name or f"audio_{message.audio.file_unique_id}.mp3", "file_size": message.audio.file_size or 0, "kind": "audio"}
    if message.voice:
        return {"file_id": message.voice.file_id, "file_name": f"voice_{message.voice.file_unique_id}.ogg", "file_size": message.voice.file_size or 0, "kind": "voice"}
    if message.photo:
        photo = message.photo[-1]
        return {"file_id": photo.file_id, "file_name": f"photo_{photo.file_unique_id}.jpg", "file_size": photo.file_size or 0, "kind": "photo"}
    return None


class LilyTools:
    def __init__(self, db: Database):
        self.db = db
        self.sem = asyncio.Semaphore(settings.max_concurrent_jobs)

    async def _download_telegram_file(self, ctx: ToolContext, target: Path) -> dict:
        message = ctx.update.effective_message
        source = ctx.source_file or source_file_from_message(message.reply_to_message if message and message.reply_to_message else message)
        if not source:
            raise ValueError("Reply to a document, video, audio, voice message, or photo.")
        size = int(source.get("file_size") or 0)
        if size > settings.max_file_bytes:
            raise ValueError(f"That file is larger than Lily’s configured limit ({settings.max_file_bytes} bytes).")
        ok, reason = await self.db.charge_bytes(ctx.update.effective_user.id, ctx.update.effective_chat.id, max(size, 1))
        if not ok:
            raise ValueError(f"File quota unavailable: {reason}.")
        await ctx.progress(f"Downloading {source['file_name']}…")
        telegram_file = await ctx.context.bot.get_file(source["file_id"])
        await telegram_file.download_to_drive(custom_path=str(target))
        actual = target.stat().st_size
        if actual > settings.max_file_bytes:
            target.unlink(missing_ok=True)
            raise ValueError("The downloaded file exceeds Lily’s configured limit.")
        return {**source, "path": target, "size": actual}

    async def rename_file(self, ctx: ToolContext, new_name: str) -> Path:
        async with self.sem:
            source_name = safe_filename(new_name)
            source = ctx.update.effective_message.reply_to_message if ctx.update.effective_message.reply_to_message else ctx.update.effective_message
            source_meta = ctx.source_file or source_file_from_message(source)
            if not source_meta:
                raise ValueError("Reply to the file you want Lily to rename.")
            old_name = source_meta["file_name"]
            old_ext = Path(old_name).suffix
            new_path_name = source_name if Path(source_name).suffix else source_name + old_ext
            target = settings.work_dir / f"{int(time.time())}_{safe_filename(new_path_name)}"
            input_path = settings.work_dir / f"input_{ctx.update.update_id}_{safe_filename(old_name)}"
            await self._download_telegram_file(ctx, input_path)
            shutil.copy2(input_path, target)
            input_path.unlink(missing_ok=True)
            return target

    async def compress_file(self, ctx: ToolContext, fmt: str = "zip") -> Path:
        async with self.sem:
            source_name = safe_filename("source.bin")
            source_message = ctx.update.effective_message.reply_to_message if ctx.update.effective_message.reply_to_message else ctx.update.effective_message
            source_meta = ctx.source_file or source_file_from_message(source_message)
            if source_meta:
                source_name = safe_filename(source_meta["file_name"])
            input_path = settings.work_dir / f"input_{ctx.update.update_id}_{source_name}"
            await self._download_telegram_file(ctx, input_path)
            if input_path.stat().st_size > settings.max_job_bytes:
                input_path.unlink(missing_ok=True)
                raise ValueError("The file is above Lily’s job-size limit.")
            output = settings.work_dir / f"{Path(source_name).stem}_compressed.zip"
            await ctx.progress("Compressing the file; this may take a while…")
            compression = zipfile.ZIP_DEFLATED
            with zipfile.ZipFile(output, "w", compression=compression, compresslevel=6, allowZip64=True) as archive:
                archive.write(input_path, arcname=source_name)
            input_path.unlink(missing_ok=True)
            return output

    async def encode_media(self, ctx: ToolContext, codec: str = "h264", container: str = "mp4") -> Path:
        async with self.sem:
            source_message = ctx.update.effective_message.reply_to_message if ctx.update.effective_message.reply_to_message else ctx.update.effective_message
            meta = ctx.source_file or source_file_from_message(source_message)
            if not meta:
                raise ValueError("Reply to a video or audio file to encode it.")
            input_path = settings.work_dir / f"encode_{ctx.update.update_id}_{safe_filename(meta['file_name'])}"
            await self._download_telegram_file(ctx, input_path)
            output = settings.work_dir / f"{input_path.stem}_encoded.{safe_filename(container, 'mp4')}"
            if codec.lower() in {"h264", "h.264", "x264"}:
                command = ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-i", str(input_path), "-c:v", "libx264", "-preset", "medium", "-crf", "23", "-c:a", "aac", str(output)]
            elif codec.lower() in {"h265", "hevc", "x265"}:
                command = ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-i", str(input_path), "-c:v", "libx265", "-preset", "medium", "-crf", "28", "-c:a", "aac", str(output)]
            elif codec.lower() in {"mp3", "aac", "opus"}:
                output = output.with_suffix(f".{codec.lower()}")
                command = ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-i", str(input_path), "-vn", "-c:a", codec.lower(), str(output)]
            else:
                input_path.unlink(missing_ok=True)
                raise ValueError("Unsupported codec. Use h264, h265, mp3, aac, or opus.")
            await ctx.progress("Encoding media with FFmpeg…")
            process = await asyncio.create_subprocess_exec(*command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            _, stderr = await process.communicate()
            input_path.unlink(missing_ok=True)
            if process.returncode != 0:
                output.unlink(missing_ok=True)
                raise RuntimeError(stderr.decode(errors="replace")[-1000:] or "FFmpeg failed")
            return output

    async def create_file(self, ctx: ToolContext, fmt: str, prompt: str, content: str | None = None) -> Path:
        async with self.sem:
            content = content or prompt
            stamp = int(time.time())
            fmt = (fmt or "txt").lower().strip(".")
            if fmt in {"txt", "md", "markdown", "json", "csv", "html"}:
                ext = "md" if fmt == "markdown" else fmt
                output = settings.work_dir / f"lily_created_{stamp}.{ext}"
                if fmt == "json":
                    try:
                        content = json.dumps(json.loads(content), indent=2, ensure_ascii=False)
                    except json.JSONDecodeError:
                        content = json.dumps({"content": content}, indent=2, ensure_ascii=False)
                elif fmt == "csv":
                    rows = [line.split(",") for line in content.splitlines() if line.strip()]
                    with output.open("w", newline="", encoding="utf-8") as handle:
                        csv.writer(handle).writerows(rows)
                    return output
                elif fmt == "html":
                    content = f"<!doctype html><html><body><pre>{content}</pre></body></html>"
                output.write_text(content, encoding="utf-8")
                return output
            if fmt == "pdf":
                from reportlab.lib.pagesizes import A4
                from reportlab.lib.styles import getSampleStyleSheet
                from reportlab.lib.units import mm
                from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer
                from xml.sax.saxutils import escape
                output = settings.work_dir / f"lily_created_{stamp}.pdf"
                doc = SimpleDocTemplate(str(output), pagesize=A4, rightMargin=18 * mm, leftMargin=18 * mm, topMargin=18 * mm, bottomMargin=18 * mm)
                styles = getSampleStyleSheet()
                story = [Paragraph("Lily-generated document", styles["Title"]), Spacer(1, 8)]
                for line in content.splitlines() or [content]:
                    story.append(Paragraph(escape(line) or " ", styles["BodyText"]))
                    story.append(Spacer(1, 4))
                doc.build(story)
                return output
            raise ValueError("Supported file formats are txt, md, json, csv, html, and pdf.")

    async def download_song(self, ctx: ToolContext, url: str, rights_confirmed: bool) -> Path:
        parsed = urlparse(url)
        host = (parsed.hostname or "").lower()
        if parsed.scheme not in {"http", "https"} or not host:
            raise ValueError("Use a valid direct HTTPS audio URL.")
        if not rights_confirmed:
            raise PermissionError("Lily needs confirmation that you have permission to download this audio.")
        if settings.permitted_download_domains and not any(host == domain or host.endswith("." + domain) for domain in settings.permitted_download_domains):
            raise PermissionError("This download domain is not allow-listed by the administrator.")
        if not settings.allow_direct_media_downloads and not settings.permitted_download_domains:
            raise PermissionError("Direct downloads are disabled. Configure an allow-list of permitted domains first.")
        output = settings.download_dir / f"lily_audio_{int(time.time())}.audio"
        total = 0
        await ctx.progress("Downloading permitted audio…")
        async with httpx.AsyncClient(follow_redirects=True, timeout=httpx.Timeout(60.0, connect=10.0)) as client:
            async with client.stream("GET", url) as response:
                response.raise_for_status()
                content_type = response.headers.get("content-type", "").lower()
                if content_type and not (content_type.startswith("audio/") or "octet-stream" in content_type):
                    raise ValueError("The URL does not appear to point to an audio file.")
                content_length = int(response.headers.get("content-length", "0") or 0)
                if content_length > settings.max_file_bytes:
                    raise ValueError("The audio file is above Lily’s configured size limit.")
                with output.open("wb") as handle:
                    async for chunk in response.aiter_bytes(1024 * 1024):
                        total += len(chunk)
                        if total > settings.max_file_bytes:
                            raise ValueError("The audio file exceeded Lily’s configured size limit.")
                        handle.write(chunk)
        return output

    async def send_output(self, ctx: ToolContext, path: Path, caption: str) -> None:
        if not path.exists():
            raise FileNotFoundError(str(path))
        await ctx.progress("Uploading the result…")
        await ctx.context.bot.send_document(chat_id=ctx.update.effective_chat.id, document=InputFile(str(path), filename=path.name), caption=caption[:1000])
        path.unlink(missing_ok=True)
