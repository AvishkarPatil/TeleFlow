from __future__ import annotations

import asyncio
import os
import re
import tempfile
import time
from datetime import date
from pathlib import Path
from typing import Optional, TYPE_CHECKING

from pyrogram.errors import ChatForwardsRestricted, ChannelPrivate, UserNotParticipant
from pyrogram.types import InputReplyToMessage

from core.media_type import MediaKind, detect, has_media, get_file_ref
from core.progress import ProgressTracker
from db import tasks as task_db
from db import logs as log_db
from db import users as user_db
from db.models import TaskDocument, TaskStatus, TransferLogDocument, SourceType, ThumbMode, UserPrefs
from utils.retry import with_retry_call, MaxRetriesExceeded
from utils.temp import managed_tempfile, cleanup_stale_files, _ensure_temp_dir
from utils.formatting import format_bytes
from logging_config import get_logger

if TYPE_CHECKING:
    from pyrogram import Client
    from pyrogram.types import Message

log = get_logger(__name__)

# Per-source-chat restriction cache: source_chat -> True (restricted) / False (not restricted)
# Shared across all tasks so range batches only probe once
_restriction_cache: dict[str, bool] = {}


class TransferError(Exception):
    pass


def _apply_caption(original: Optional[str], prefs: UserPrefs) -> Optional[str]:
    if prefs.caption_template is not None:
        if prefs.caption_template == "":
            return None
        result = prefs.caption_template.replace("{caption}", original or "")
        result = result.replace("{date}", date.today().isoformat())
        return result.strip() or None
    if original and prefs.caption_filters:
        result = original
        for word in prefs.caption_filters:
            result = re.sub(re.escape(word), "", result, flags=re.IGNORECASE)
        return result.strip() or None
    return original


def _apply_filename(original: Optional[str], prefs: UserPrefs, task: TaskDocument) -> Optional[str]:
    if not prefs.filename_template or not original:
        return original
    p = Path(original)
    result = (
        prefs.filename_template
        .replace("{filename}", p.stem)
        .replace("{ext}", p.suffix.lstrip("."))
        .replace("{date}", date.today().isoformat())
        .replace("{id}", task.task_id)
        .replace("{chat}", str(task.source_chat))
    )
    if p.suffix and "{ext}" not in prefs.filename_template:
        result = result + p.suffix
    return result.strip()


async def _extract_video_thumb(video_path: str, task_id: str) -> Optional[str]:
    try:
        import shutil
        if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
            return None

        thumb_path = os.path.join(tempfile.gettempdir(), f"stf_thumb_{task_id}.jpg")

        # Get duration async
        probe = await asyncio.create_subprocess_exec(
            "ffprobe", "-v", "error", "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1", video_path,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL,
        )
        stdout, _ = await asyncio.wait_for(probe.communicate(), timeout=10)
        try:
            duration = float(stdout.decode().strip())
        except (ValueError, AttributeError):
            duration = 0
        seek = max(0, duration / 2)

        # Extract frame async
        proc = await asyncio.create_subprocess_exec(
            "ffmpeg", "-ss", str(seek), "-i", video_path,
            "-vframes", "1", "-q:v", "2", "-y", thumb_path,
            stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL,
        )
        await asyncio.wait_for(proc.communicate(), timeout=30)
        return thumb_path if os.path.exists(thumb_path) and os.path.getsize(thumb_path) > 0 else None
    except Exception:
        return None


async def _resolve_thumb(prefs: UserPrefs, media_obj: object, user_acc: "Client", task_id: str, video_path: Optional[str] = None) -> Optional[str]:
    if prefs.thumbnail_mode == ThumbMode.NONE:
        # Extract middle frame from video
        if video_path:
            return await _extract_video_thumb(video_path, task_id)
        return None
    if prefs.thumbnail_mode == ThumbMode.CUSTOM and prefs.thumbnail_file_id:
        tmp = os.path.join(tempfile.gettempdir(), f"stf_thumb_{task_id}.jpg")
        try:
            await user_acc.download_media(prefs.thumbnail_file_id, file_name=tmp)
            return tmp if os.path.exists(tmp) else None
        except Exception:
            return None
    # ThumbMode.DEFAULT — use original thumb from source
    thumbs = getattr(media_obj, "thumbs", None)
    if thumbs:
        thumb_path = _ensure_temp_dir() / f"{task_id}_thumb.jpg"
        try:
            await user_acc.download_media(thumbs[-1], file_name=str(thumb_path))
            return str(thumb_path) if thumb_path.exists() else None
        except Exception:
            return None
    return None


def _parse_chat(source_chat: str):
    try:
        return int(source_chat)
    except ValueError:
        return source_chat


def _kind_to_suffix(kind: MediaKind) -> str:
    return {
        MediaKind.VIDEO: ".mp4", MediaKind.AUDIO: ".mp3",
        MediaKind.VOICE: ".ogg", MediaKind.ANIMATION: ".mp4",
        MediaKind.STICKER: ".webp", MediaKind.PHOTO: ".jpg",
        MediaKind.DOCUMENT: "",
    }.get(kind, "")


async def _fetch_via_user(user_acc: "Client", source_chat: str, msg_id: int, task_id: str) -> Optional["Message"]:
    try:
        msg = await with_retry_call(user_acc.get_messages, _parse_chat(source_chat), msg_id, task_id=task_id)
        return msg if msg and not msg.empty else None
    except (ChannelPrivate, UserNotParticipant) as e:
        raise TransferError(f"Cannot access {source_chat}: {type(e).__name__}")
    except Exception:
        return None


async def _upload(task, bot, user_acc, source_msg, kind, file_path, tracker, reply_to_msg_id, prefs):
    chat_id = task.status_chat_id
    media_obj = get_file_ref(source_msg)
    caption = _apply_caption(source_msg.caption, prefs)
    caption_entities = None if (prefs.caption_template is not None or prefs.caption_filters) \
                       else source_msg.caption_entities
    file_name = _apply_filename(getattr(media_obj, "file_name", None), prefs, task)
    video_path = str(file_path) if kind == MediaKind.VIDEO else None
    thumb = await _resolve_thumb(prefs, media_obj, user_acc, task.task_id, video_path=video_path)
    common = dict(reply_parameters=InputReplyToMessage(message_id=reply_to_msg_id), progress=tracker.on_upload)

    try:
        if kind == MediaKind.PHOTO:
            await with_retry_call(bot.send_photo, chat_id, photo=str(file_path),
                caption=caption, caption_entities=caption_entities, task_id=task.task_id, **common)
        elif kind == MediaKind.VIDEO:
            vid = source_msg.video
            await with_retry_call(bot.send_video, chat_id, video=str(file_path),
                duration=vid.duration, width=vid.width, height=vid.height,
                thumb=thumb, caption=caption, caption_entities=caption_entities,
                task_id=task.task_id, **common)
        elif kind == MediaKind.DOCUMENT:
            await with_retry_call(bot.send_document, chat_id, document=str(file_path),
                thumb=thumb, file_name=file_name, caption=caption, caption_entities=caption_entities,
                task_id=task.task_id, **common)
        elif kind == MediaKind.AUDIO:
            aud = source_msg.audio
            await with_retry_call(bot.send_audio, chat_id, audio=str(file_path),
                duration=aud.duration, performer=aud.performer, title=aud.title,
                thumb=thumb, caption=caption, caption_entities=caption_entities,
                task_id=task.task_id, **common)
        elif kind == MediaKind.VOICE:
            await with_retry_call(bot.send_voice, chat_id, voice=str(file_path),
                duration=source_msg.voice.duration, caption=caption, caption_entities=caption_entities,
                task_id=task.task_id, **common)
        elif kind == MediaKind.ANIMATION:
            await with_retry_call(bot.send_animation, chat_id, animation=str(file_path),
                caption=caption, caption_entities=caption_entities, task_id=task.task_id, **common)
        elif kind == MediaKind.STICKER:
            await with_retry_call(bot.send_sticker, chat_id, sticker=str(file_path),
                task_id=task.task_id,
                reply_parameters=InputReplyToMessage(message_id=reply_to_msg_id))
        else:
            raise TransferError(f"Unsupported media kind: {kind.value}")
    finally:
        if thumb and "stf_thumb_" in thumb:
            try:
                os.remove(thumb)
            except OSError:
                pass


async def _download_and_upload(task, bot, user_acc, source_msg, kind, tracker, reply_to_msg_id, prefs):
    async with managed_tempfile(task.task_id, _kind_to_suffix(kind)) as tmp_path:
        log.info("transfer.downloading", task_id=task.task_id, kind=kind.value, size=format_bytes(task.file_size or 0))
        await with_retry_call(
            user_acc.download_media, source_msg,
            file_name=str(tmp_path), progress=tracker.on_download,
            task_id=task.task_id,
        )
        if not tmp_path.exists() or tmp_path.stat().st_size == 0:
            raise TransferError("Download failed — file is empty. Try again.")
        await task_db.update_task(task.task_id, msg_id_current=task.msg_id_start)
        log.info("transfer.uploading", task_id=task.task_id, kind=kind.value)
        await _upload(task, bot, user_acc, source_msg, kind, tmp_path, tracker, reply_to_msg_id, prefs)


async def _finalise(task, tracker, start_time, file_size, success, error_msg=None):
    elapsed = time.monotonic() - start_time
    avg_bps = file_size / elapsed if elapsed > 0 else 0.0
    await task_db.set_task_status(
        task.task_id,
        TaskStatus.DONE if success else TaskStatus.FAILED,
        error=error_msg, msg_id_current=task.msg_id_current,
    )
    await tracker.send_final_edit(success=success, elapsed=elapsed, file_size=file_size, error_msg=error_msg)
    await log_db.log_transfer(TransferLogDocument(
        task_id=task.task_id, user_id=task.user_id,
        source_chat=task.source_chat, msg_id=task.msg_id_start,
        media_type=task.media_type or "unknown", file_name=task.file_name,
        file_size=file_size, duration_seconds=elapsed, avg_speed_bps=avg_bps,
        success=success, error=error_msg,
    ))
    if success and file_size > 0:
        await user_db.increment_task_stats(task.user_id, file_size)
    log.info("transfer.finalised", task_id=task.task_id, success=success,
             duration=f"{elapsed:.1f}s", size=format_bytes(file_size))


async def execute(task: TaskDocument, bot: "Client", user_acc: Optional["Client"], reply_to_msg_id: int) -> None:
    start_time = time.monotonic()
    cleanup_stale_files(task.task_id)
    await task_db.set_task_status(task.task_id, TaskStatus.RUNNING)

    user_chat_id = task.user_chat_id or task.status_chat_id
    dest_chat_id = task.status_chat_id

    prefs = await user_db.get_prefs(task.user_id)

    # Always fetch via user session — fastest, full access, no wasted bot attempt
    if user_acc is None:
        raise TransferError("User session not configured. Set USER_SESSION_STRING.")

    source_msg = await _fetch_via_user(user_acc, task.source_chat, task.msg_id_start, task.task_id)

    status_msg = await bot.send_message(
        user_chat_id, "⏳  Fetching…",
        reply_parameters=InputReplyToMessage(message_id=reply_to_msg_id),
    )
    await task_db.update_task(task.task_id, status_msg_id=status_msg.id, status_chat_id=user_chat_id)
    tracker = ProgressTracker(bot=bot, task=task, status_chat_id=user_chat_id, status_msg_id=status_msg.id)

    error_msg: Optional[str] = None
    success = False
    transferred_bytes = 0

    try:
        if source_msg is None:
            raise TransferError(f"Message {task.msg_id_start} not found or inaccessible.")

        kind = detect(source_msg)
        media_obj = get_file_ref(source_msg)
        file_size = getattr(media_obj, "file_size", 0) or 0
        file_name = getattr(media_obj, "file_name", None)

        await task_db.update_task(task.task_id, media_type=kind.value, file_size=file_size, file_name=file_name)
        task.media_type = kind.value
        task.file_size = file_size
        task.file_name = file_name
        transferred_bytes = file_size

        # Text-only message
        if not has_media(source_msg):
            if source_msg.text or source_msg.caption:
                await bot.send_message(
                    dest_chat_id,
                    source_msg.text or source_msg.caption,
                    entities=source_msg.entities or source_msg.caption_entities,
                )
            await bot.delete_messages(user_chat_id, [status_msg.id])
            await task_db.set_task_status(task.task_id, TaskStatus.DONE)
            success = True
            return

        # Check restriction cache — probed once per source chat, reused for entire range
        cache_key = task.source_chat
        if cache_key not in _restriction_cache:
            # Probe: try copy_message to detect restriction
            try:
                await with_retry_call(
                    bot.copy_message,
                    dest_chat_id, source_msg.chat.id, source_msg.id,
                    task_id=task.task_id,
                )
                _restriction_cache[cache_key] = False  # not restricted
                success = True
                await bot.delete_messages(user_chat_id, [status_msg.id])
                await _finalise(task, tracker, start_time, file_size, success=True)
                return
            except ChatForwardsRestricted:
                _restriction_cache[cache_key] = True  # restricted — cache it
                log.info("transfer.restricted_cached", source=cache_key)
            except Exception:
                _restriction_cache[cache_key] = True  # assume restricted on any failure

        if not _restriction_cache[cache_key]:
            # Not restricted — bot mode: try copy first
            if prefs.bot_mode:
                try:
                    await with_retry_call(
                        bot.copy_message,
                        dest_chat_id, source_msg.chat.id, source_msg.id,
                        task_id=task.task_id,
                    )
                    success = True
                    await bot.delete_messages(user_chat_id, [status_msg.id])
                    await _finalise(task, tracker, start_time, file_size, success=True)
                    return
                except Exception:
                    pass
            else:
                # Default: user session copy (no forward tag)
                try:
                    await with_retry_call(source_msg.copy, dest_chat_id, task_id=task.task_id)
                    success = True
                    await bot.delete_messages(user_chat_id, [status_msg.id])
                    await _finalise(task, tracker, start_time, file_size, success=True)
                    return
                except Exception:
                    pass

        # Restricted — go straight to download/upload, no copy attempt
        task.status_chat_id = dest_chat_id
        await _download_and_upload(task, bot, user_acc, source_msg, kind, tracker, reply_to_msg_id, prefs)
        success = True

    except TransferError as e:
        error_msg = str(e)
        log.error("transfer.failed", task_id=task.task_id, error=error_msg)
    except MaxRetriesExceeded as e:
        error_msg = f"Failed after {e.attempts} retries: {e.last_error}"
        log.error("transfer.max_retries", task_id=task.task_id, error=error_msg)
    except Exception as e:
        error_msg = f"{type(e).__name__}: {e}"
        log.exception("transfer.unexpected_error", task_id=task.task_id)
    finally:
        task.status_chat_id = user_chat_id
        await _finalise(task, tracker, start_time, transferred_bytes, success, error_msg)
