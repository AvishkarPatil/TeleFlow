from __future__ import annotations

from pyrogram import filters
from pyrogram.types import Message


async def _sudo_check(_, __, message: Message) -> bool:
    if not message.from_user:
        return False
    from db.users import is_sudo_user
    return await is_sudo_user(message.from_user.id)


sudo = filters.create(_sudo_check, "SudoFilter")
