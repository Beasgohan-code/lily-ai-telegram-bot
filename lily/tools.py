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
from typing import Any, Awaitable, Callable
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


def _ensure_dirs() -> None:
    settings.work_dir.mkdir(parents=True, exist_ok=True)
    settings.download_dir.mkdir(parents=True, exist_ok=True)


def _assert_under(base: Path, target: Path) -> Path:
    """Reject path traversal — target must resolve under base."""
    base_r = base.resolve()
    target_r = target.resolve()
    if not str(target_r).startswith(str(base_r)):
        raise ValueError("Lily refused a path outside its managed work directory.")
    return target_r


def _public_tool_error(exc: BaseException) -> str:
    """Never leak stack traces or absolute host paths to chat."""
    text = str(exc) or type(exc).__name__
    text = re.sub(r"/[^\s:]{8,}", "[path]", text)
    text = re.sub(r"(?i)(api[_ -]?key|token|secret|password)\s*[:=]\s*\S+", r"\1=[redacted]", text)
    return text[:500]


async def _retry(
    label: str,
    fn: Callable[[], Awaitable[Any]],
    *,
    attempts: int | None = None,
    progress: Callable[[str], Awaitable[Any]] | None = None,
) -> Any:
    """Retry transient failures (network / Telegram download) with brief backoff."""
    tries = settings.tool_retry_count + 1 if attempts is None else max(1, attempts)
    last: BaseException | None = None
    for i in range(tries):
        try:
            return await fn()
        except (httpx.TransportError, httpx.TimeoutException, ConnectionError, TimeoutError, OSError) as exc:
            last = exc
            if i >= tries - 1:
                break
            if progress:
                await progress(f"{label} failed, retrying ({i + 1}/{tries - 1})…")
            await asyncio.sleep(min(2 ** i, 8))
        except Exception:
            raise
    raise RuntimeError(_public_tool_error(last or RuntimeError(f"{label} failed")))


class LilyTools:
    def __init__(self, db: Database):
        self.db = db
        self.sem = asyncio.Semaphore(settings.max_concurrent_jobs)
        _ensure_dirs()

    async def _run_subprocess(self, command: list[str], *, timeout: int | None = None) -> tuple[int, bytes, bytes]:
        """Run ffmpeg/ffprobe with a hard timeout so jobs cannot hang forever."""
        limit = timeout if timeout is not None else settings.tool_subprocess_timeout
        process = await asyncio.create_subprocess_exec(
            *command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        try:
            stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=limit)
        except asyncio.TimeoutError:
            process.kill()
            await process.wait()
            raise TimeoutError(f"Tool timed out after {limit}s.")
        return process.returncode or 0, stdout or b"", stderr or b""

    async def _download_telegram_file(self, ctx: ToolContext, target: Path) -> dict:
        _ensure_dirs()
        target = _assert_under(settings.work_dir, target)
        message = ctx.update.effective_message
        source = ctx.source_file or source_file_from_message(
            message.reply_to_message if message and message.reply_to_message else message
        )
        if not source:
            raise ValueError("Reply to a document, video, audio, voice message, or photo.")
        size = int(source.get("file_size") or 0)
        if size > settings.max_file_bytes:
            raise ValueError(f"That file is larger than Lily’s configured limit ({settings.max_file_bytes} bytes).")
        ok, reason = await self.db.charge_bytes(ctx.update.effective_user.id, ctx.update.effective_chat.id, max(size, 1))
        if not ok:
            raise ValueError(f"File quota unavailable: {reason}.")

        async def _once() -> dict:
            await ctx.progress(f"Downloading {source['file_name']}…")
            telegram_file = await ctx.context.bot.get_file(source["file_id"])
            await telegram_file.download_to_drive(custom_path=str(target))
            if not target.exists():
                raise RuntimeError("Download completed but the file is missing.")
            actual = target.stat().st_size
            if actual > settings.max_file_bytes:
                target.unlink(missing_ok=True)
                raise ValueError("The downloaded file exceeds Lily’s configured limit.")
            return {**source, "path": target, "size": actual}

        try:
            return await _retry("Telegram download", _once, progress=ctx.progress)
        except Exception as exc:
            target.unlink(missing_ok=True)
            raise type(exc)(_public_tool_error(exc)) from None

    async def rename_file(self, ctx: ToolContext, new_name: str) -> Path:
        async with self.sem:
            _ensure_dirs()
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
            target = _assert_under(settings.work_dir, target)
            shutil.copy2(input_path, target)
            input_path.unlink(missing_ok=True)
            return target

    async def media_info(self, ctx: ToolContext) -> dict:
        async with self.sem:
            _ensure_dirs()
            source = ctx.update.effective_message.reply_to_message if ctx.update.effective_message.reply_to_message else ctx.update.effective_message
            meta = ctx.source_file or source_file_from_message(source)
            if not meta:
                raise ValueError("Reply to a media file so Lily can inspect it.")
            input_path = settings.work_dir / f"info_{ctx.update.update_id}_{safe_filename(meta['file_name'])}"
            await self._download_telegram_file(ctx, input_path)
            command = [
                "ffprobe", "-v", "error", "-show_entries",
                "format=duration,size,bit_rate,format_name:stream=codec_name,codec_type,width,height,sample_rate,channels",
                "-of", "json", str(input_path),
            ]
            await ctx.progress("Inspecting media…")
            try:
                code, stdout, stderr = await self._run_subprocess(command, timeout=min(120, settings.tool_subprocess_timeout))
            finally:
                input_path.unlink(missing_ok=True)
            if code != 0:
                raise RuntimeError(_public_tool_error(RuntimeError(stderr.decode(errors="replace")[-800:] or "FFprobe failed")))
            try:
                return json.loads(stdout.decode("utf-8"))
            except json.JSONDecodeError as exc:
                raise RuntimeError("FFprobe returned invalid metadata.") from exc

    async def compress_file(self, ctx: ToolContext, fmt: str = "zip") -> Path:
        async with self.sem:
            _ensure_dirs()
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
            output = _assert_under(settings.work_dir, output)
            await ctx.progress("Compressing the file; this may take a while…")
            try:
                with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6, allowZip64=True) as archive:
                    archive.write(input_path, arcname=source_name)
            except Exception:
                output.unlink(missing_ok=True)
                raise
            finally:
                input_path.unlink(missing_ok=True)
            return output

    async def encode_media(self, ctx: ToolContext, codec: str = "h264", container: str = "mp4") -> Path:
        async with self.sem:
            _ensure_dirs()
            source_message = ctx.update.effective_message.reply_to_message if ctx.update.effective_message.reply_to_message else ctx.update.effective_message
            meta = ctx.source_file or source_file_from_message(source_message)
            if not meta:
                raise ValueError("Reply to a video or audio file to encode it.")
            input_path = settings.work_dir / f"encode_{ctx.update.update_id}_{safe_filename(meta['file_name'])}"
            await self._download_telegram_file(ctx, input_path)
            output = settings.work_dir / f"{input_path.stem}_encoded.{safe_filename(container, 'mp4')}"
            codec_l = codec.lower()
            if codec_l in {"h264", "h.264", "x264"}:
                command = ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-i", str(input_path), "-c:v", "libx264", "-preset", "medium", "-crf", "23", "-c:a", "aac", str(output)]
            elif codec_l in {"h265", "hevc", "x265"}:
                command = ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-i", str(input_path), "-c:v", "libx265", "-preset", "medium", "-crf", "28", "-c:a", "aac", str(output)]
            elif codec_l in {"mp3", "aac", "opus"}:
                output = output.with_suffix(f".{codec_l}")
                command = ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-i", str(input_path), "-vn", "-c:a", codec_l if codec_l != "mp3" else "libmp3lame", str(output)]
            else:
                input_path.unlink(missing_ok=True)
                raise ValueError("Supported codecs: h264, h265, mp3, aac, opus.")
            output = _assert_under(settings.work_dir, output)
            await ctx.progress(f"Encoding with {codec}…")
            try:
                code, _stdout, stderr = await self._run_subprocess(command)
                if code != 0 or not output.exists():
                    raise RuntimeError(stderr.decode(errors="replace")[-800:] or "FFmpeg encoding failed")
            except Exception as exc:
                output.unlink(missing_ok=True)
                raise RuntimeError(_public_tool_error(exc)) from None
            finally:
                input_path.unlink(missing_ok=True)
            return output

    async def create_file(self, ctx: ToolContext, name: str, content: str, fmt: str = "txt") -> Path:
        async with self.sem:
            _ensure_dirs()
            safe_name = safe_filename(name)
            fmt_l = (fmt or "txt").lower().lstrip(".")
            if fmt_l not in {"txt", "md", "markdown", "json", "csv", "html", "pdf"}:
                raise ValueError("Supported formats: txt, md, json, csv, html, pdf.")
            if fmt_l == "markdown":
                fmt_l = "md"
            if not safe_name.lower().endswith(f".{fmt_l}"):
                safe_name = f"{safe_name}.{fmt_l}"
            target = _assert_under(settings.work_dir, settings.work_dir / f"{int(time.time())}_{safe_name}")
            body = content or ""
            if len(body.encode("utf-8")) > settings.max_file_bytes:
                raise ValueError("Generated content exceeds Lily’s file size limit.")
            await ctx.progress(f"Creating {safe_name}…")
            if fmt_l == "pdf":
                try:
                    from reportlab.lib.pagesizes import letter
                    from reportlab.pdfgen import canvas
                except ImportError as exc:
                    raise RuntimeError("PDF generation requires reportlab.") from exc
                c = canvas.Canvas(str(target), pagesize=letter)
                width, height = letter
                y = height - 40
                for line in body.splitlines() or [""]:
                    c.drawString(40, y, line[:110])
                    y -= 14
                    if y < 40:
                        c.showPage()
                        y = height - 40
                c.save()
            elif fmt_l == "json":
                try:
                    parsed = json.loads(body) if body.strip() else {}
                except json.JSONDecodeError:
                    parsed = {"text": body}
                target.write_text(json.dumps(parsed, indent=2, ensure_ascii=False), encoding="utf-8")
            elif fmt_l == "csv":
                rows = [row.split(",") for row in body.splitlines() if row.strip()]
                with target.open("w", encoding="utf-8", newline="") as handle:
                    writer = csv.writer(handle)
                    for row in rows or [["column"]]:
                        writer.writerow(row)
            else:
                target.write_text(body, encoding="utf-8")
            return target

    async def download_song(self, ctx: ToolContext, url: str, rights_confirmed: bool = False) -> Path:
        if not settings.allow_direct_media_downloads:
            raise ValueError("Direct audio downloads are disabled by the administrator.")
        if not rights_confirmed:
            raise ValueError("Rights confirmation is required before Lily downloads audio.")
        parsed = urlparse(url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("Provide a direct HTTP(S) audio URL.")
        host = parsed.netloc.lower().split(":")[0]
        allowed = settings.permitted_download_domains
        if allowed and not any(host == d or host.endswith("." + d) for d in allowed):
            raise ValueError("That domain is not on the administrator allow-list.")
        _ensure_dirs()
        suffix = Path(parsed.path).suffix.lower() or ".mp3"
        if suffix not in {".mp3", ".m4a", ".ogg", ".flac", ".wav", ".aac", ".opus"}:
            suffix = ".mp3"
        output = settings.download_dir / f"audio_{int(time.time())}{suffix}"
        output = _assert_under(settings.download_dir, output)
        total = 0
        await ctx.progress("Downloading permitted audio…")

        async def _once() -> Path:
            nonlocal total
            total = 0
            timeout = httpx.Timeout(float(settings.tool_download_timeout), connect=15.0)
            async with httpx.AsyncClient(follow_redirects=True, timeout=timeout) as client:
                async with client.stream("GET", url) as response:
                    response.raise_for_status()
                    content_type = response.headers.get("content-type", "").split(";", 1)[0].lower()
                    if content_type and not any(t in content_type for t in ("audio", "octet-stream", "mpeg", "ogg", "wav", "flac")):
                        raise ValueError("The source did not return an audio file.")
                    content_length = int(response.headers.get("content-length", "0") or 0)
                    if content_length > settings.max_file_bytes:
                        raise ValueError("The audio file exceeds Lily’s configured size limit.")
                    with output.open("wb") as handle:
                        async for chunk in response.aiter_bytes(1024 * 1024):
                            total += len(chunk)
                            if total > settings.max_file_bytes:
                                raise ValueError("The audio file exceeded Lily’s configured size limit.")
                            handle.write(chunk)
            return output

        try:
            return await _retry("Audio download", _once, progress=ctx.progress)
        except Exception as exc:
            output.unlink(missing_ok=True)
            raise type(exc)(_public_tool_error(exc)) from None

    async def download_chapter_file(self, ctx: ToolContext, url: str, title: str = "series", chapter: str = "chapter") -> Path:
        if not settings.allow_direct_chapter_downloads:
            raise ValueError("Direct chapter downloads are disabled by the administrator.")
        parsed = urlparse(url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("Provide a direct HTTP(S) chapter URL.")
        host = parsed.netloc.lower().split(":")[0]
        allowed = settings.allowed_chapter_domains
        if allowed and not any(host == d or host.endswith("." + d) for d in allowed):
            raise ValueError("That domain is not on the administrator chapter allow-list.")
        _ensure_dirs()
        safe_title = safe_filename(title, "series")
        safe_chapter = safe_filename(chapter, "chapter")
        suffix = Path(parsed.path).suffix.lower()
        if suffix not in {".pdf", ".cbz", ".zip"}:
            suffix = ".bin"
        output = settings.download_dir / f"{safe_title}_chapter_{safe_chapter}{suffix}"
        output = _assert_under(settings.download_dir, output)
        total = 0
        allowed_types = {
            "application/pdf",
            "application/zip",
            "application/x-cbz",
            "application/vnd.comicbook+zip",
            "application/octet-stream",
        }
        await ctx.progress("Retrieving the approved chapter file…")

        async def _once() -> Path:
            nonlocal total
            total = 0
            timeout = httpx.Timeout(float(settings.tool_download_timeout), connect=15.0)
            async with httpx.AsyncClient(follow_redirects=True, timeout=timeout) as client:
                async with client.stream("GET", url) as response:
                    response.raise_for_status()
                    content_type = response.headers.get("content-type", "").split(";", 1)[0].lower()
                    if content_type and content_type not in allowed_types:
                        raise ValueError("The source did not return an approved PDF, ZIP, or CBZ chapter file.")
                    content_length = int(response.headers.get("content-length", "0") or 0)
                    if content_length > settings.max_file_bytes:
                        raise ValueError("The chapter file exceeds Lily’s configured size limit.")
                    with output.open("wb") as handle:
                        async for chunk in response.aiter_bytes(1024 * 1024):
                            total += len(chunk)
                            if total > settings.max_file_bytes:
                                raise ValueError("The chapter file exceeded Lily’s configured size limit.")
                            handle.write(chunk)
            return output

        try:
            return await _retry("Chapter download", _once, progress=ctx.progress)
        except Exception as exc:
            output.unlink(missing_ok=True)
            raise type(exc)(_public_tool_error(exc)) from None

    async def send_output(self, ctx: ToolContext, path: Path, caption: str) -> None:
        if not path.exists():
            raise FileNotFoundError("The generated file is missing.")
        # Bound path to managed dirs
        try:
            _assert_under(settings.work_dir, path)
        except ValueError:
            _assert_under(settings.download_dir, path)
        await ctx.progress("Uploading the result…")
        try:
            await ctx.context.bot.send_document(
                chat_id=ctx.update.effective_chat.id,
                document=InputFile(str(path), filename=path.name),
                caption=(caption or "")[:1000],
            )
        finally:
            path.unlink(missing_ok=True)
