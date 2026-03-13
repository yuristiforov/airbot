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

MSG_UV_HIGH      = "☀️ Высокий UV-индекс ({uv:.0f}). Надень солнцезащитный крем."
MSG_UV_EXTREME   = "🔆 Экстремальный UV-индекс ({uv:.0f})! Не выходи без защиты кожи и глаз."
MSG_UV_CLEAR     = "☁️ UV-индекс нормализовался ({uv:.0f}). Можно выходить без крема."

UV_HIGH    = 6.0
UV_EXTREME = 11.0


def _is_daytime_utc() -> bool:
    """Rough check: UTC hour between 6 and 20 (covers most latitudes at peak UV)."""
    return 6 <= datetime.now(timezone.utc).hour <= 20


async def check_and_notify_uv(bot: Bot, user: dict, current_uv: float) -> None:
    if not user.get("track_uv", True):
        return

    user_id = user["user_id"]
    state = await get_alert_state(user_id)
    prev_status = state.get("uv_status") if state else None

    new_status: str
    message: str | None = None

    if current_uv >= UV_EXTREME:
        new_status = "extreme"
        if prev_status != "extreme":
            message = MSG_UV_EXTREME.format(uv=current_uv)
    elif current_uv >= UV_HIGH:
        new_status = "high"
        if prev_status not in ("high", "extreme"):
            message = MSG_UV_HIGH.format(uv=current_uv)
    else:
        new_status = "safe"
        if prev_status in ("high", "extreme") and _is_daytime_utc():
            message = MSG_UV_CLEAR.format(uv=current_uv)

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
