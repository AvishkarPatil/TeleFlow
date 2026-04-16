from __future__ import annotations

from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup


def start_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📋  ʜᴏᴡ ᴛᴏ ᴜꜱᴇ", callback_data="help")],
        [
            InlineKeyboardButton("📂  ᴍʏ ᴛᴀꜱᴋꜱ", callback_data="tasks"),
            InlineKeyboardButton("⚙️  ꜱᴇᴛᴛɪɴɢꜱ", callback_data="s:main"),
        ],
        [InlineKeyboardButton("🖥  ꜱʏꜱᴛᴇᴍ", callback_data="system")],
    ])


def help_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("‹  ʙᴀᴄᴋ", callback_data="back_start")],
    ])


def system_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("👥  ᴜꜱᴇʀꜱ", callback_data="users"),
            InlineKeyboardButton("⚙️  ᴄᴏɴꜰɪɢ", callback_data="config"),
        ],
        [InlineKeyboardButton("‹  ʙᴀᴄᴋ", callback_data="back_start")],
    ])


def system_back_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("‹  ʙᴀᴄᴋ", callback_data="system")],
    ])


def tasks_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("↻  ʀᴇꜰʀᴇꜱʜ", callback_data="tasks")],
        [InlineKeyboardButton("‹  ʙᴀᴄᴋ", callback_data="back_start")],
    ])


def cancel_keyboard(task_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("✕  ᴄᴀɴᴄᴇʟ", callback_data=f"cancel:{task_id}")],
    ])


def confirm_cancel_keyboard(task_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("ʏᴇꜱ, ᴄᴀɴᴄᴇʟ", callback_data=f"cancel_confirm:{task_id}"),
            InlineKeyboardButton("ɴᴏ", callback_data="dismiss"),
        ],
    ])
