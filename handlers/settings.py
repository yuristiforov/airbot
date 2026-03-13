from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message
from db import get_user, set_user_active, set_user_alert, set_user_track
from air_api import waqi_client

router = Router()


@router.message(Command("status"))
async def cmd_status(message: Message) -> None:
    user = await get_user(message.from_user.id)
    if not user or not user.get("city_name"):
        await message.answer("Ты ещё не настроил город. Используй /start.")
        return

    result = await waqi_client.get_aqi_by_coords(user["lat"], user["lon"])
    if result is None:
        await message.answer(
            f"Город: {user['city_name']}\nДанные о качестве воздуха сейчас недоступны."
        )
        return

    await message.answer(
        f"Город: {user['city_name']}\nAQI сейчас: {result['aqi']}"
    )


@router.message(Command("settings"))
async def cmd_settings(message: Message) -> None:
    user = await get_user(message.from_user.id)
    if not user or not user.get("city_name"):
        await message.answer("Ты ещё не настроил город. Используй /start.")
        return

    active_str = "включены" if user["active"] else "выключены"
    alert_100_str = "вкл" if user["alert_100"] else "выкл"
    alert_150_str = "вкл" if user["alert_150"] else "выкл"
    track_air_str = "вкл" if user.get("track_air", True) else "выкл"
    track_uv_str = "вкл" if user.get("track_uv", True) else "выкл"
    track_weather_str = "вкл" if user.get("track_weather", True) else "выкл"

    await message.answer(
        f"Настройки:\n"
        f"Город: {user['city_name']}\n"
        f"Алерты: {active_str}\n\n"
        f"Отслеживание:\n"
        f"  Воздух (AQI): {track_air_str}\n"
        f"    Предупреждение (>= 100): {alert_100_str}\n"
        f"    Опасность (>= 150): {alert_150_str}\n"
        f"  UV-индекс: {track_uv_str}\n"
        f"  Экстремальная погода: {track_weather_str}\n\n"
        f"Команды:\n"
        f"/stop — приостановить все алерты\n"
        f"/resume — возобновить алерты\n"
        f"/start — сменить город"
    )


@router.message(Command("stop"))
async def cmd_stop(message: Message) -> None:
    user = await get_user(message.from_user.id)
    if not user:
        await message.answer("Ты ещё не зарегистрирован. Используй /start.")
        return

    await set_user_active(message.from_user.id, False)
    await message.answer("Алерты приостановлены. Используй /resume, чтобы возобновить.")


@router.message(Command("resume"))
async def cmd_resume(message: Message) -> None:
    user = await get_user(message.from_user.id)
    if not user:
        await message.answer("Ты ещё не зарегистрирован. Используй /start.")
        return

    await set_user_active(message.from_user.id, True)
    await message.answer("Алерты возобновлены. Буду присылать уведомления об изменениях.")
