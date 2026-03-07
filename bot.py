import asyncio
import logging
import os
from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
from config import settings
from db import init_db
from scheduler import setup_scheduler
from handlers import start, settings as settings_handler, location

logging.basicConfig(
    level=getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO),
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


async def main() -> None:
    os.makedirs(settings.DATA_DIR, exist_ok=True)

    await init_db()
    logger.info("Database initialized at %s", settings.db_path)

    bot = Bot(token=settings.BOT_TOKEN)
    dp = Dispatcher(storage=MemoryStorage())

    dp.include_router(start.router)
    dp.include_router(settings_handler.router)
    dp.include_router(location.router)

    scheduler = setup_scheduler(bot)

    async def on_startup() -> None:
        scheduler.start()
        logger.info("Scheduler started")

    async def on_shutdown() -> None:
        scheduler.shutdown(wait=False)
        logger.info("Scheduler stopped")
        await bot.session.close()

    dp.startup.register(on_startup)
    dp.shutdown.register(on_shutdown)

    logger.info("Starting polling...")
    await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())


if __name__ == "__main__":
    asyncio.run(main())
