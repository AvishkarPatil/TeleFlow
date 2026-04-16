from __future__ import annotations

import asyncio
from typing import Callable, TypeVar, Awaitable, Any

from logging_config import get_logger

log = get_logger(__name__)
T = TypeVar("T")
_MAX_FLOOD_WAIT = 300

_NON_RETRYABLE = (
    "MediaEmpty", "MessageIdInvalid", "ChannelInvalid",
    "ChannelPrivate", "ChatForbidden", "UserNotParticipant", "FilerefUpgradeNeeded",
    "ValueError", "ChatForwardsRestricted",
)


class MaxRetriesExceeded(Exception):
    def __init__(self, attempts: int, last_error: Exception):
        self.attempts = attempts
        self.last_error = last_error
        super().__init__(f"Failed after {attempts} attempts: {last_error}")


async def with_retry_call(
    func: Callable[..., Awaitable[T]],
    *args: Any,
    max_retries: int = 5,
    base_delay: float = 2.0,
    task_id: str | None = None,
    **kwargs: Any,
) -> T:
    kwargs.pop("task_id", None)
    from pyrogram.errors import FloodWait

    attempt = 0
    last_error: Exception = RuntimeError("No attempts made")

    while attempt < max_retries:
        try:
            return await func(*args, **kwargs)

        except FloodWait as e:
            wait = min(e.value + 1, _MAX_FLOOD_WAIT)
            log.warning("flood_wait", task_id=task_id, wait_seconds=wait, func=func.__name__)
            await asyncio.sleep(wait)

        except Exception as e:
            err_name = type(e).__name__
            if err_name in _NON_RETRYABLE:
                log.debug("non_retryable_error", task_id=task_id, error=err_name, func=func.__name__)
                raise

            last_error = e
            attempt += 1
            delay = base_delay * (2 ** (attempt - 1))
            log.warning(
                "retryable_error",
                task_id=task_id, error=err_name, detail=str(e),
                attempt=attempt, max_retries=max_retries,
                next_delay=f"{delay:.1f}s", func=func.__name__,
            )
            if attempt >= max_retries:
                break
            await asyncio.sleep(delay)

    raise MaxRetriesExceeded(attempt, last_error)
