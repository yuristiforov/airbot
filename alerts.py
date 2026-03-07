import logging
from aiogram import Bot
from db import get_alert_state, update_alert_state

logger = logging.getLogger(__name__)

MSG_WARNING = "⚠️ Воздух грязный (AQI {aqi}). Лишний раз не выходи из дома."
MSG_DANGER = "🚨 Опасно! AQI {aqi}. Сиди дома, закрой окна и вентиляцию."
MSG_CLEAR = "✅ Воздух улучшился (AQI {aqi}). Опасность отменена."


async def check_and_notify(bot: Bot, user: dict, current_aqi: int) -> None:
    user_id = user["user_id"]
    state = await get_alert_state(user_id)
    prev_status = state["last_status"] if state else None

    new_status: str
    message: str | None = None

    if current_aqi >= 150:
        new_status = "danger"
        if prev_status != "danger":
            if user.get("alert_150", True):
                message = MSG_DANGER.format(aqi=current_aqi)
    elif current_aqi >= 100:
        new_status = "warning"
        if prev_status not in ("warning", "danger"):
            if user.get("alert_100", True):
                message = MSG_WARNING.format(aqi=current_aqi)
    else:
        new_status = "clear"
        if prev_status in ("warning", "danger"):
            message = MSG_CLEAR.format(aqi=current_aqi)

    if message:
        try:
            await bot.send_message(user_id, message)
            logger.info("Sent %s alert to user %d (AQI %d)", new_status, user_id, current_aqi)
        except Exception as exc:
            logger.warning("Failed to send alert to user %d: %s", user_id, exc)

    await update_alert_state(user_id, current_aqi, new_status)
