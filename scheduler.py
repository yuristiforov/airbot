import logging
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from aiogram import Bot
from db import get_all_active_users
from air_api import waqi_client
from uv_api import get_uv_index
from weather_api import get_current_weather
from alerts import check_and_notify, check_and_notify_uv, check_and_notify_weather

logger = logging.getLogger(__name__)


async def hourly_check(bot: Bot) -> None:
    users = await get_all_active_users()
    logger.info("Hourly check: processing %d active users", len(users))
    for user in users:
        lat, lon = user["lat"], user["lon"]
        user_id = user["user_id"]
        try:
            # Air quality
            if user.get("track_air", True):
                result = await waqi_client.get_aqi_by_coords(lat, lon)
                if result is not None:
                    await check_and_notify(bot, user, result["aqi"])
                else:
                    logger.debug("No AQI data for user %d (%s)", user_id, user["city_name"])

            # UV index
            if user.get("track_uv", True):
                uv = await get_uv_index(lat, lon)
                if uv is not None:
                    await check_and_notify_uv(bot, user, uv)
                else:
                    logger.debug("No UV data for user %d", user_id)

            # Extreme weather
            if user.get("track_weather", True):
                weather = await get_current_weather(lat, lon)
                if weather is not None:
                    await check_and_notify_weather(bot, user, weather)
                else:
                    logger.debug("No weather data for user %d", user_id)

        except Exception as exc:
            logger.error("Error processing user %d: %s", user_id, exc)


def setup_scheduler(bot: Bot) -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler()
    scheduler.add_job(
        hourly_check,
        trigger=IntervalTrigger(hours=1),
        kwargs={"bot": bot},
        id="hourly_check",
        replace_existing=True,
        max_instances=1,
    )
    return scheduler
