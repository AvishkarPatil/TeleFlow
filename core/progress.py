from __future__ import annotations

import asyncio
import time
from typing import Optional, TYPE_CHECKING

from pyrogram import enums
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from utils.formatting import format_bytes, format_speed, format_eta, format_percent, format_duration, truncate

if TYPE_CHECKING:
    from pyrogram import Client
    from db.models import TaskDocument

EDIT_INTERVAL = 4.0
_PM = enums.ParseMode.HTML

_MEDIA_ICON = {
    "video": "🎬", "photo": "🖼", "document": "📄",
    "audio": "🎵", "voice": "🎙", "animation": "🎞", "sticker": "🪄",
}


def _bar(current: int, total: int, width: int = 10) -> str:
    if total <= 0:
        return "□" * width
    filled = int(width * current / total)
    return "■" * filled + "□" * (width - filled)


def _cancel_kb(task_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("✕  ᴄᴀɴᴄᴇʟ", callback_data=f"cancel:{task_id}")],
    ])


class ProgressTracker:
    def __init__(self, bot: "Client", task: "TaskDocument", status_chat_id: int, status_msg_id: int) -> None:
        self._bot = bot
        self._task = task
        self._chat_id = status_chat_id
        self._msg_id = status_msg_id
        self.phase = "download"
        self.current: int = 0
        self.total: int = 0
        self._phase_start = time.monotonic()
        self._last_edit: float = 0.0
        self._lock = asyncio.Lock()

    async def on_download(self, current: int, total: int) -> None:
        self.current, self.total = current, total
        if self.phase != "download":
            self.phase = "download"
            self._phase_start = time.monotonic()
        await self._maybe_edit()

    async def on_upload(self, current: int, total: int) -> None:
        self.current, self.total = current, total
        if self.phase != "upload":
            self.phase = "upload"
            self._phase_start = time.monotonic()
        await self._maybe_edit()

    async def _maybe_edit(self) -> None:
        now = time.monotonic()
        if now - self._last_edit < EDIT_INTERVAL:
            return
        async with self._lock:
            now = time.monotonic()
            if now - self._last_edit < EDIT_INTERVAL:
                return
            self._last_edit = now
        await self._do_edit()

    async def _do_edit(self) -> None:
        try:
            await self._bot.edit_message_text(
                self._chat_id, self._msg_id, self._render(),
                parse_mode=_PM,
                reply_markup=_cancel_kb(self._task.task_id),
            )
        except Exception:
            pass

    def _render(self) -> str:
        elapsed = max(0.01, time.monotonic() - self._phase_start)
        bps = self.current / elapsed if elapsed > 0 else 0.0
        task = self._task
        icon = _MEDIA_ICON.get(task.media_type or "", "📁")
        name = truncate(task.file_name or task.source_chat or "—", 35)
        total_size = format_bytes(task.file_size or self.total or 0)
        done_size = format_bytes(self.current)
        bar = _bar(self.current, self.total)
        pct = format_percent(self.current, self.total)
        phase = "⬇️ Downloading" if self.phase == "download" else "⬆️ Uploading"

        return (
            f"{icon}  <b>{name}</b>\n"
            f"\n"
            f"{phase}\n"
            f"\n"
            f"┣  [{bar}]  {pct}\n"
            f"┣  {done_size}  /  {total_size}\n"
            f"┣  <b>Speed :</b>  {format_speed(bps)}\n"
            f"┗  <b>ETA   :</b>  {format_eta(self.current, self.total, bps)}\n"
            f"\n"
            f"<code>{task.task_id}</code>"
        )

    async def send_final_edit(
        self,
        success: bool,
        elapsed: float,
        file_size: int,
        error_msg: Optional[str] = None,
    ) -> None:
        task = self._task
        avg_bps = file_size / elapsed if elapsed > 0 else 0.0
        icon = _MEDIA_ICON.get(task.media_type or "", "📁")

        if success:
            name = truncate(task.file_name or "untitled", 40)
            text = (
                f"{icon}  <b>{name}</b>\n"
                f"\n"
                f"┣  <b>Size :</b>      {format_bytes(file_size)}\n"
                f"┣  <b>Duration :</b>  {format_duration(elapsed)}\n"
                f"┗  <b>Avg speed :</b> {format_speed(avg_bps)}"
            )
        else:
            text = (
                f"<b><i>Transfer failed</i></b>\n"
                f"\n"
                f"┣  <b>Task :</b>  <code>{task.task_id}</code>\n"
                f"┗  <b><i>{error_msg or 'Unknown error'}</i></b>"
            )

        # Delete progress message and send fresh final — avoids MessageNotModified stuck state
        try:
            await self._bot.delete_messages(self._chat_id, [self._msg_id])
        except Exception:
            pass
        try:
            await self._bot.send_message(self._chat_id, text, parse_mode=_PM)
        except Exception:
            pass
