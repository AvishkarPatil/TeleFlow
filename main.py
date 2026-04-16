from __future__ import annotations

import asyncio
import signal
import sys

from logging_config import configure_logging, get_logger

configure_logging()
log = get_logger(__name__)


def _install_uvloop() -> None:
    try:
        import uvloop
        uvloop.install()
        log.info("event_loop.uvloop_installed")
    except ImportError:
        log.info("event_loop.using_default", reason="uvloop not available (Windows?)")

_install_uvloop()

from config import settings
from db.connection import init_db, close_db
from db.tasks import mark_all_running_as_interrupted
from db.users import seed_sudo_users
from bot.client import bot, user_acc
from core.task_queue import queue

from bot.handlers import commands  # noqa: F401
from bot.handlers import messages  # noqa: F401
from bot.handlers import settings as _settings_handlers  # noqa: F401


async def _start_health_server() -> None:
    try:
        from aiohttp import web

        async def health(_request: web.Request) -> web.Response:
            return web.json_response({
                "status": "ok",
                "workers": queue.worker_count(),
                "queue_depth": queue.queue_depth(),
            })

        app = web.Application()
        app.router.add_get("/health", health)
        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, "0.0.0.0", settings.health_port)
        await site.start()
        log.info("health_server.started", port=settings.health_port)
    except Exception as e:
        log.warning("health_server.failed", error=str(e))


async def main() -> None:
    log.info("savethefile.starting", version="2.0.0")

    await init_db()
    interrupted_count = await mark_all_running_as_interrupted()
    if interrupted_count:
        log.warning("startup.tasks_interrupted", count=interrupted_count)
    await seed_sudo_users()

    await bot.start()
    log.info("bot.started", username=(await bot.get_me()).username)

    if user_acc is not None:
        await user_acc.start()
        log.info("user_account.started")

    await queue.start(bot=bot, user_acc=user_acc)

    if settings.enable_health_server:
        await _start_health_server()

    log.info("savethefile.ready", workers=settings.max_workers)

    stop_event = asyncio.Event()

    def _signal_handler(sig: signal.Signals) -> None:
        log.info("savethefile.shutdown_signal", signal=sig.name)
        stop_event.set()

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, _signal_handler, sig)
        except NotImplementedError:
            pass

    await stop_event.wait()

    log.info("savethefile.shutting_down")
    await queue.stop(drain_timeout=120.0)

    if user_acc is not None:
        await user_acc.stop()
        log.info("user_account.stopped")

    await bot.stop()
    log.info("bot.stopped")

    await close_db()
    log.info("savethefile.shutdown_complete")


if __name__ == "__main__":
    try:
        loop = asyncio.get_event_loop()
        loop.run_until_complete(main())
    except KeyboardInterrupt:
        log.info("savethefile.keyboard_interrupt")
        sys.exit(0)
