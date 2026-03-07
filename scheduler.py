import logging
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from aiogram import Bot
from db import get_all_active_users
from air_api import waqi_client
from alerts import check_and_notify

logger = logging.getLogger(__name__)


async def hourly_check(bot: Bot) -> None:
    users = await get_all_active_users()
    logger.info("Hourly check: processing %d active users", len(users))
    for user in users:
        try:
            result = await waqi_client.get_aqi_by_coords(user["lat"], user["lon"])
            if result is None:
                logger.debug("No AQI data for user %d (%s)", user["user_id"], user["city_name"])
                continue
            await check_and_notify(bot, user, result["aqi"])
        except Exception as exc:
            logger.error("Error processing user %d: %s", user["user_id"], exc)


def setup_scheduler(bot: Bot) -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler()
    scheduler.add_job(
        hourly_check,
        trigger=IntervalTrigger(hours=1),
        kwargs={"bot": bot},
        id="hourly_aqi_check",
        replace_existing=True,
        max_instances=1,
    )
    return scheduler
