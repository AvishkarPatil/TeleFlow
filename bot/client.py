from __future__ import annotations

from typing import Optional

from pyrogram import Client

from config import settings
from logging_config import get_logger

log = get_logger(__name__)

bot = Client(
    name="savethefile_bot",
    api_id=settings.telegram_api_id,
    api_hash=settings.telegram_api_hash,
    bot_token=settings.bot_token,
    in_memory=True,
    workers=8,
    max_concurrent_transmissions=4,
    sleep_threshold=60,
)

user_acc: Optional[Client] = None

if settings.user_session_string:
    user_acc = Client(
        name="savethefile_user",
        api_id=settings.telegram_api_id,
        api_hash=settings.telegram_api_hash,
        session_string=settings.user_session_string,
        in_memory=True,
        workers=8,
        max_concurrent_transmissions=10,
        sleep_threshold=60,
    )
    log.info("user_account.configured")
else:
    log.warning("user_account.not_configured")
