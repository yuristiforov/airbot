import logging
from datetime import datetime, timezone
from aiogram import Bot
from db import get_alert_state, update_alert_state, update_uv_alert_state, update_weather_alert_state

logger = logging.getLogger(__name__)

# ── Air quality ───────────────────────────────────────────────────────────────

MSG_AIR_WARNING = "⚠️ Воздух грязный (AQI {aqi}). Лишний раз не выходи из дома."
MSG_AIR_DANGER  = "🚨 Опасно! AQI {aqi}. Сиди дома, закрой окна и вентиляцию."
MSG_AIR_CLEAR   = "✅ Воздух улучшился (AQI {aqi}). Опасность отменена."


async def check_and_notify(bot: Bot, user: dict, current_aqi: int) -> None:
    if not user.get("track_air", True):
        return

    user_id = user["user_id"]
    state = await get_alert_state(user_id)
    prev_status = state["last_status"] if state else None

    new_status: str
    message: str | None = None

    if current_aqi >= 150:
        new_status = "danger"
        if prev_status != "danger":
            if user.get("alert_150", True):
                message = MSG_AIR_DANGER.format(aqi=current_aqi)
    elif current_aqi >= 100:
        new_status = "warning"
        if prev_status not in ("warning", "danger"):
            if user.get("alert_100", True):
                message = MSG_AIR_WARNING.format(aqi=current_aqi)
    else:
        new_status = "clear"
        if prev_status in ("warning", "danger"):
            message = MSG_AIR_CLEAR.format(aqi=current_aqi)

    if message:
        try:
            await bot.send_message(user_id, message)
            logger.info("Sent air %s alert to user %d (AQI %d)", new_status, user_id, current_aqi)
        except Exception as exc:
            logger.warning("Failed to send air alert to user %d: %s", user_id, exc)

    await update_alert_state(user_id, current_aqi, new_status)


# ── UV index ──────────────────────────────────────────────────────────────────

MSG_UV_LOW    = "☀️ UV низкий ({uv:.0f}). Защита не требуется."
MSG_UV_MEDIUM = "🕶 UV умеренный ({uv:.0f}). Используйте крем с SPF и солнцезащитные очки."
MSG_UV_HIGH   = "🔆 UV высокий ({uv:.0f}). Лучше не выходите из дома. Если необходимо — держитесь в тени, закрывайте все открытые участки кожи."

UV_MEDIUM = 3.0
UV_HIGH   = 8.0


def _is_daytime_utc() -> bool:
    """Rough check: UTC hour between 6 and 20 (covers most latitudes at peak UV)."""
    return 6 <= datetime.now(timezone.utc).hour <= 20


def _uv_zone(uv: float) -> str:
    if uv >= UV_HIGH:
        return "high"
    if uv >= UV_MEDIUM:
        return "medium"
    return "low"


async def check_and_notify_uv(bot: Bot, user: dict, current_uv: float) -> None:
    if not user.get("track_uv", True):
        return

    user_id = user["user_id"]
    state = await get_alert_state(user_id)
    prev_status = state.get("uv_status") if state else None

    new_status = _uv_zone(current_uv)
    message: str | None = None

    if new_status != prev_status:
        if new_status == "high":
            message = MSG_UV_HIGH.format(uv=current_uv)
        elif new_status == "medium":
            # LOW→MEDIUM or HIGH→MEDIUM both get the medium alert
            message = MSG_UV_MEDIUM.format(uv=current_uv)
        else:  # new_status == "low"
            if _is_daytime_utc():
                message = MSG_UV_LOW.format(uv=current_uv)

    if message:
        try:
            await bot.send_message(user_id, message)
            logger.info("Sent UV %s alert to user %d (UV %.1f)", new_status, user_id, current_uv)
        except Exception as exc:
            logger.warning("Failed to send UV alert to user %d: %s", user_id, exc)

    await update_uv_alert_state(user_id, current_uv, new_status)


# ── Extreme weather ───────────────────────────────────────────────────────────

MSG_WEATHER_ALERT = "⛈ Экстремальная погода! Ветер {wind:.0f} км/ч, код погоды: {code}. Будь осторожен."
MSG_WEATHER_CLEAR = "🌤 Экстремальная погода миновала. Условия нормализовались."


async def check_and_notify_weather(bot: Bot, user: dict, weather: dict) -> None:
    if not user.get("track_weather", True):
        return

    user_id = user["user_id"]
    state = await get_alert_state(user_id)
    prev_status = state.get("weather_status") if state else None

    is_extreme = weather["is_extreme"]
    weather_code = weather["weather_code"]
    wind_speed = weather["wind_speed"]

    new_status: str
    message: str | None = None

    if is_extreme:
        new_status = "alert"
        if prev_status != "alert":
            message = MSG_WEATHER_ALERT.format(wind=wind_speed, code=weather_code)
    else:
        new_status = "clear"
        if prev_status == "alert":
            message = MSG_WEATHER_CLEAR

    if message:
        try:
            await bot.send_message(user_id, message)
            logger.info("Sent weather %s alert to user %d (code %d, wind %.1f)", new_status, user_id, weather_code, wind_speed)
        except Exception as exc:
            logger.warning("Failed to send weather alert to user %d: %s", user_id, exc)

    await update_weather_alert_state(user_id, weather_code, new_status)
