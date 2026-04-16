from __future__ import annotations

from pyrogram import filters, enums
from pyrogram.errors import UserAlreadyParticipant, InviteHashExpired, InviteHashInvalid
from pyrogram.types import Message

from bot.client import bot, user_acc
from bot.filters import sudo
from bot.handlers.settings import _AWAITING as _SETTINGS_AWAITING
from core.link_parser import parse, ParsedLink
from core.task_queue import queue
from db.models import SourceType
from db import users as user_db
from logging_config import get_logger

log = get_logger(__name__)
_PM = enums.ParseMode.HTML


@bot.on_message(sudo & filters.text & ~filters.command([
    "start", "help", "status", "tasks", "cancel",
    "adduser", "removeuser", "users", "settings", "system",
]), group=0)
async def handle_text(_: object, message: Message) -> None:
    uid = message.from_user.id if message.from_user else None
    if not uid:
        return

    if uid in _SETTINGS_AWAITING:
        return

    text = message.text.strip()

    if message.from_user:
        await user_db.upsert_user(uid, message.from_user.username, message.from_user.first_name or "")

    if "https://t.me/+" in text or "https://t.me/joinchat/" in text:
        await _handle_invite(message, text)
        return

    if "https://t.me/" in text:
        await _handle_link(message, text)
        return


async def _handle_invite(message: Message, url: str) -> None:
    if user_acc is None:
        await message.reply(
            "⚠️  User session not configured.\n"
            "Set <code>USER_SESSION_STRING</code> to join private chats.",
            parse_mode=_PM,
        )
        return

    parsed = parse(url)
    if parsed is None or not parsed.invite_hash:
        await message.reply("Couldn't parse that invite link.", parse_mode=_PM)
        return

    try:
        await user_acc.join_chat(url)
        await message.reply("<b><i>✓  Joined the chat. You can now send post links from it.</i></b>", parse_mode=_PM)
        log.info("chat.joined", invite_hash=parsed.invite_hash[:6] + "…", user=message.from_user.id)
    except UserAlreadyParticipant:
        await message.reply("<b><i>Already a member of that chat.</i></b>", parse_mode=_PM)
    except (InviteHashExpired, InviteHashInvalid):
        await message.reply("<b><i>⚠️  Invite link is invalid or expired.</i></b>", parse_mode=_PM)
    except Exception as e:
        await message.reply(f"<b><i>⚠️  Failed to join.</i></b>\n<code>{type(e).__name__}: {e}</code>", parse_mode=_PM)


async def _handle_link(message: Message, url: str) -> None:
    parsed: ParsedLink | None = parse(url)

    if parsed is None:
        await message.reply(
            "<b><i>⚠️  Couldn't parse that link.</i></b>\n"
            "Tap <b>How to use</b> for supported formats.",
            parse_mode=_PM,
        )
        return

    if parsed.source_type == SourceType.INVITE:
        await _handle_invite(message, url)
        return

    if parsed.source_type in (SourceType.PRIVATE, SourceType.BOT) and user_acc is None:
        await message.reply(
            "<b><i>⚠️  User session not configured.</i></b>\n"
            "Private channels require <code>USER_SESSION_STRING</code>.",
            parse_mode=_PM,
        )
        return

    uid = message.from_user.id
    prefs = await user_db.get_prefs(uid)
    user_chat_id = message.chat.id
    dest_chat_id = prefs.dest_channel_id or user_chat_id

    # Send queued message first so we have its ID
    dest_note = f"\n<i>→ {prefs.dest_channel_title}</i>" if prefs.dest_channel_id else ""
    count = parsed.message_count

    if count == 1:
        queued_msg = await message.reply(
            f"<b><i>↻  Queued</i></b>{dest_note}",
            parse_mode=_PM,
        )
    else:
        queued_msg = await message.reply(
            f"<b><i>↻  Queued  ·  {count} messages</i></b>{dest_note}",
            parse_mode=_PM,
        )

    try:
        task_ids = await queue.enqueue(
            parsed=parsed,
            user_id=uid,
            dest_chat_id=dest_chat_id,
            user_chat_id=user_chat_id,
            reply_to_msg_id=message.id,
            queued_msg_id=queued_msg.id,
        )
    except RuntimeError as e:
        await queued_msg.delete()
        await message.reply(f"<b><i>⚠️  {e}</i></b>", parse_mode=_PM)
        return

    # Edit to show task ID
    try:
        if count == 1:
            await queued_msg.edit_text(
                f"<b><i>↻  Queued</i></b>  ·  <code>{task_ids[0]}</code>{dest_note}",
                parse_mode=_PM,
            )
    except Exception:
        pass

    log.info("tasks.enqueued", count=count, source=f"{parsed.source_chat}/{parsed.msg_id_start}", user=uid)
