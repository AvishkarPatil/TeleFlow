from __future__ import annotations

from pyrogram import filters, enums
from pyrogram.errors import MessageNotModified
from pyrogram.types import Message, CallbackQuery

from bot.client import bot
from bot.filters import sudo
from bot.keyboards import (
    start_keyboard, help_keyboard,
    system_keyboard, system_back_keyboard, tasks_keyboard,
)
from config import settings
from core.task_queue import queue
from db import users as user_db
from db import tasks as task_db
from db.models import TaskStatus
from utils.formatting import format_bytes
from logging_config import get_logger

log = get_logger(__name__)

_PM = enums.ParseMode.HTML


async def _edit(cb: CallbackQuery, text: str, **kwargs) -> None:
    try:
        await cb.message.edit_text(text, parse_mode=_PM, **kwargs)
    except MessageNotModified:
        pass

_STATUS_ICON = {
    TaskStatus.DONE:        "✓",
    TaskStatus.FAILED:      "✕",
    TaskStatus.INTERRUPTED: "⊘",
    TaskStatus.CANCELLED:   "–",
    TaskStatus.RUNNING:     "↻",
    TaskStatus.QUEUED:      "·",
}

_MEDIA_ICON = {
    "video": "🎬", "photo": "🖼", "document": "📄",
    "audio": "🎵", "voice": "🎙", "animation": "🎞", "sticker": "🪄",
}


# ── Text builders ─────────────────────────────────────────────────────────────


def _start_text(name: str, bot_username: str, user_id: int) -> str:
    return (
        f"Hey <a href=\"tg://user?id={user_id}\"><b>{name}</b></a> 👋\n"
        "\n"
        "<b><i>I'm your personal media saver —\nready to grab anything from Telegram.</i></b>\n"
        "\n"
        "<blockquote>•  Restricted &amp; private channels\n•  Videos, docs, audio &amp; more\n•  Custom filename, caption &amp; destination</blockquote>\n"
        f"with 💕  @{bot_username}"
    )


def _help_text() -> str:
    return (
        "<b>How to use</b>\n"
        "\n"
        "Paste a post link — I'll fetch the media.\n"
        "\n"
        "<b>Single post</b>\n"
        "•  <b>Public :</b>   <code>t.me/channel/123</code>\n"
        "•  <b>Private :</b>  <code>t.me/c/1234567890/45</code>\n"
        "•  <b>Bot :</b>      <code>t.me/b/botname/78</code>\n"
        "\n"
        "<b>Range of posts</b>\n"
        "•  <code>t.me/channel/100-110</code>\n"
        "\n"
        "<b>Private chat access</b>\n"
        "•  Send the invite link first\n"
        "•  <code>t.me/+AbCdEfGhIj</code>"
    )


def _system_text() -> str:
    session = "● Connected" if settings.user_session_string else "○ Not set"
    workers = queue.worker_count()
    total = settings.max_workers
    depth = queue.queue_depth()
    bar_filled = int(10 * workers / total) if total else 0
    bar = "■" * bar_filled + "□" * (10 - bar_filled)
    return (
        "<b>System</b>\n"
        "\n"
        f"•  <b>Workers :</b>  [{bar}]  {workers}/{total}\n"
        f"•  <b>Queue :</b>    {depth} pending\n"
        f"•  <b>Session :</b>  {session}"
    )


def _config_text() -> str:
    health = "On" if settings.enable_health_server else "Off"
    return (
        "<b>Config</b>\n"
        "\n"
        f"•  <b>Max workers :</b>    <code>{settings.max_workers}</code>\n"
        f"•  <b>Tasks / user :</b>   <code>{settings.max_tasks_per_user}</code>\n"
        f"•  <b>Log level :</b>      <code>{settings.log_level}</code>\n"
        f"•  <b>Health server :</b>  <code>{health}</code>"
    )


async def _tasks_text(user_id: int) -> str:
    recent = await task_db.get_recent_tasks(user_id, limit=10)
    if not recent:
        return (
            "<b>My Tasks</b>\n"
            "\n"
            "<i>No tasks yet.</i>\n"
            "Drop a link to get started."
        )
    lines = ["<b>My Tasks</b>\n"]
    for t in recent:
        icon = _STATUS_ICON.get(t.status, "?")
        micon = _MEDIA_ICON.get(t.media_type or "", "📁")
        size = format_bytes(t.file_size) if t.file_size else "—"
        src = t.source_chat if len(t.source_chat) <= 18 else t.source_chat[:16] + "…"
        lines.append(f"•  {icon} {micon}  <code>{t.task_id}</code>  ·  <b>{src}</b>  ·  <i>{size}</i>")
    return "\n".join(lines)


async def _users_text() -> str:
    sudo_users = await user_db.list_sudo_users()
    if not sudo_users:
        return "<b>Users</b>\n\n<i>No authorised users.</i>"
    lines = [f"<b>Users</b>  ·  {len(sudo_users)} total\n"]
    for u in sudo_users:
        name = f"@{u.username}" if u.username else u.first_name or "—"
        stats = f"{u.total_tasks} tasks · {format_bytes(u.total_bytes_transferred)}"
        lines.append(f"•  <b>ID :</b>  <code>{u.user_id}</code>  ·  {name}  ·  <i>{stats}</i>")
    return "\n".join(lines)


# ── Commands ──────────────────────────────────────────────────────────────────


@bot.on_message(sudo & filters.command("start"))
async def cmd_start(_: object, message: Message) -> None:
    name = message.from_user.first_name or "there"
    me = await bot.get_me()
    await message.reply(_start_text(name, me.username, message.from_user.id), reply_markup=start_keyboard(), parse_mode=_PM)


@bot.on_message(sudo & filters.command("help"))
async def cmd_help(_: object, message: Message) -> None:
    await message.reply(_help_text(), reply_markup=help_keyboard(), parse_mode=_PM)


@bot.on_message(sudo & filters.command("system"))
async def cmd_system(_: object, message: Message) -> None:
    await message.reply(_system_text(), reply_markup=system_keyboard(), parse_mode=_PM)


@bot.on_message(sudo & filters.command("status"))
async def cmd_status(_: object, message: Message) -> None:
    active = await task_db.get_all_active_tasks()
    if not active:
        await message.reply("<b><i>No active tasks right now.</i></b>", parse_mode=_PM)
        return
    lines = [f"↻  <b>Active  ·  {len(active)} task(s)</b>\n"]
    for t in active:
        micon = _MEDIA_ICON.get(t.media_type or "", "📁")
        size = format_bytes(t.file_size or 0) if t.file_size else "—"
        lines.append(f"  {micon}  <code>{t.task_id}</code>  ·  {t.source_chat}/{t.msg_id_start}  ·  {size}")
    lines.append(f"\n<i>Queue: {queue.queue_depth()} pending</i>")
    await message.reply("\n".join(lines), parse_mode=_PM)


@bot.on_message(sudo & filters.command("tasks"))
async def cmd_tasks(_: object, message: Message) -> None:
    await message.reply(await _tasks_text(message.from_user.id),
                        reply_markup=tasks_keyboard(), parse_mode=_PM)


@bot.on_message(sudo & filters.command("cancel"))
async def cmd_cancel(_: object, message: Message) -> None:
    args = message.command[1:]
    if not args:
        await message.reply("Usage: <code>/cancel &lt;task_id&gt;</code>", parse_mode=_PM)
        return
    task_id = args[0].upper()
    cancelled = await queue.cancel_task(task_id, message.from_user.id)
    if not cancelled:
        # Try direct DB cancel for running tasks
        from db import tasks as task_db_direct
        task = await task_db_direct.get_task(task_id)
        if task and task.user_id == message.from_user.id:
            from db.models import TaskStatus as TS
            if task.status not in (TS.DONE, TS.FAILED, TS.CANCELLED, TS.INTERRUPTED):
                await task_db_direct.set_task_status(task_id, TS.CANCELLED)
                cancelled = True
    if cancelled:
        await message.reply(f"<b><i>Task <code>{task_id}</code> cancelled.</i></b>", parse_mode=_PM)
    else:
        await message.reply(f"<b><i>Task <code>{task_id}</code> not found or already finished.</i></b>", parse_mode=_PM)


@bot.on_message(sudo & filters.command("adduser"))
async def cmd_adduser(_: object, message: Message) -> None:
    args = message.command[1:]
    if not args or not args[0].isdigit():
        await message.reply("Usage: <code>/adduser &lt;user_id&gt;</code>", parse_mode=_PM)
        return
    target_id = int(args[0])
    added = await user_db.add_sudo(target_id, granted_by=message.from_user.id)
    if added:
        await message.reply(f"<b><i>✓  User <code>{target_id}</code> — access granted.</i></b>", parse_mode=_PM)
        log.info("admin.adduser", target=target_id, by=message.from_user.id)
    else:
        await message.reply(f"<b><i>User <code>{target_id}</code> already has access.</i></b>", parse_mode=_PM)


@bot.on_message(sudo & filters.command("removeuser"))
async def cmd_removeuser(_: object, message: Message) -> None:
    args = message.command[1:]
    if not args or not args[0].isdigit():
        await message.reply("Usage: <code>/removeuser &lt;user_id&gt;</code>", parse_mode=_PM)
        return
    target_id = int(args[0])
    if target_id == message.from_user.id:
        await message.reply("<b><i>You can't revoke your own access.</i></b>", parse_mode=_PM)
        return
    removed = await user_db.remove_sudo(target_id)
    if removed:
        await message.reply(f"<b><i>✓  User <code>{target_id}</code> — access revoked.</i></b>", parse_mode=_PM)
        log.info("admin.removeuser", target=target_id, by=message.from_user.id)
    else:
        await message.reply(f"<b><i>User <code>{target_id}</code> not in the access list.</i></b>", parse_mode=_PM)


@bot.on_message(sudo & filters.command("users"))
async def cmd_users(_: object, message: Message) -> None:
    await message.reply(await _users_text(), reply_markup=system_back_keyboard(), parse_mode=_PM)


# ── Callbacks ─────────────────────────────────────────────────────────────────


@bot.on_callback_query(filters.regex(r"^help$"))
async def cb_help(_: object, cb: CallbackQuery) -> None:
    await cb.answer()
    await _edit(cb, _help_text(), reply_markup=help_keyboard())


@bot.on_callback_query(filters.regex(r"^system$"))
async def cb_system(_: object, cb: CallbackQuery) -> None:
    await cb.answer()
    await _edit(cb, _system_text(), reply_markup=system_keyboard())


@bot.on_callback_query(filters.regex(r"^config$"))
async def cb_config(_: object, cb: CallbackQuery) -> None:
    await cb.answer()
    await _edit(cb, _config_text(), reply_markup=system_back_keyboard())


@bot.on_callback_query(filters.regex(r"^users$"))
async def cb_users(_: object, cb: CallbackQuery) -> None:
    await cb.answer()
    await _edit(cb, await _users_text(), reply_markup=system_back_keyboard())


@bot.on_callback_query(filters.regex(r"^tasks$"))
async def cb_tasks(_: object, cb: CallbackQuery) -> None:
    await cb.answer()
    await _edit(cb, await _tasks_text(cb.from_user.id), reply_markup=tasks_keyboard())


@bot.on_callback_query(filters.regex(r"^back_start$"))
async def cb_back_start(_: object, cb: CallbackQuery) -> None:
    await cb.answer()
    name = cb.from_user.first_name or "there"
    me = await bot.get_me()
    await _edit(cb, _start_text(name, me.username, cb.from_user.id), reply_markup=start_keyboard())


@bot.on_callback_query(filters.regex(r"^cancel:(.+)$"))
async def cb_cancel(_: object, cb: CallbackQuery) -> None:
    task_id = cb.matches[0].group(1)
    cancelled = await queue.cancel_task(task_id, cb.from_user.id)
    if cancelled:
        await cb.answer("Cancelled.", show_alert=True)
        try:
            await cb.message.edit_reply_markup(None)
        except Exception:
            pass
    else:
        await cb.answer("Already finished.", show_alert=True)
        try:
            await cb.message.edit_reply_markup(None)
        except Exception:
            pass


@bot.on_callback_query(filters.regex(r"^dismiss$"))
async def cb_dismiss(_: object, cb: CallbackQuery) -> None:
    await cb.answer()
    await cb.message.edit_reply_markup(None)
