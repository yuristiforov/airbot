from aiogram import Router, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    Message,
    CallbackQuery,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)
from timezonefinder import TimezoneFinder
from db import get_user, set_user_active, set_user_track, set_night_mode_enabled, set_night_mode_time
from air_api import waqi_client
from handlers.start import OnboardingStates, location_keyboard

_tf = TimezoneFinder()


class SettingsStates(StatesGroup):
    waiting_for_night_time = State()

router = Router()


def _track_row(label: str, enabled: bool, callback: str) -> list[InlineKeyboardButton]:
    toggle = InlineKeyboardButton(
        text="✅ Вкл" if enabled else "❌ Выкл",
        callback_data=callback,
    )
    return [InlineKeyboardButton(text=label, callback_data="settings:noop"), toggle]


def settings_keyboard(user: dict) -> InlineKeyboardMarkup:
    night_enabled = user.get("night_mode_enabled", False)
    night_start = user.get("night_start", 23)
    night_end = user.get("night_end", 7)

    rows = [
        [
            InlineKeyboardButton(
                text=f"📍 Город: {user['city_name']}",
                callback_data="settings:noop",
            ),
            InlineKeyboardButton(text="Изменить", callback_data="settings:change_city"),
        ],
        _track_row("💨 Качество воздуха", user.get("track_air", True), "settings:toggle:track_air"),
        _track_row("☀️ UV-индекс", user.get("track_uv", True), "settings:toggle:track_uv"),
        _track_row("🌪 Экстремальная погода", user.get("track_weather", True), "settings:toggle:track_weather"),
        _track_row("🌙 Ночной режим", night_enabled, "settings:toggle:night_mode"),
    ]

    if night_enabled:
        rows.append([
            InlineKeyboardButton(
                text=f"⏰ Время: {night_start:02d}:00 - {night_end:02d}:00",
                callback_data="settings:noop",
            ),
            InlineKeyboardButton(text="Изменить", callback_data="settings:night_time"),
        ])

    return InlineKeyboardMarkup(inline_keyboard=rows)


def settings_text(user: dict) -> str:
    active_str = "включены" if user["active"] else "приостановлены"
    return (
        "Настройки\n\n"
        f"Алерты: {active_str}\n\n"
        "Мониторинг:"
    )


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

    await message.answer(settings_text(user), reply_markup=settings_keyboard(user))


@router.callback_query(F.data == "settings:toggle:night_mode")
async def cb_toggle_night_mode(callback: CallbackQuery) -> None:
    user = await get_user(callback.from_user.id)
    if not user:
        await callback.answer("Сначала настрой бота через /start.")
        return

    new_val = not user.get("night_mode_enabled", False)
    await set_night_mode_enabled(callback.from_user.id, new_val)

    user = await get_user(callback.from_user.id)
    await callback.message.edit_text(settings_text(user), reply_markup=settings_keyboard(user))
    await callback.answer()


@router.callback_query(F.data == "settings:night_time")
async def cb_night_time(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(SettingsStates.waiting_for_night_time)
    await callback.message.answer(
        "Введи время начала и конца ночного режима в формате ЧЧ-ЧЧ, например: 23-7"
    )
    await callback.answer()


@router.message(SettingsStates.waiting_for_night_time)
async def msg_night_time(message: Message, state: FSMContext) -> None:
    text = (message.text or "").strip()
    parts = text.split("-")
    if len(parts) != 2:
        await message.answer("Неверный формат. Введи время в виде ЧЧ-ЧЧ, например: 23-7")
        return
    try:
        night_start = int(parts[0])
        night_end = int(parts[1])
    except ValueError:
        await message.answer("Неверный формат. Введи время в виде ЧЧ-ЧЧ, например: 23-7")
        return
    if not (0 <= night_start <= 23 and 0 <= night_end <= 23):
        await message.answer("Часы должны быть в диапазоне 0–23. Попробуй ещё раз.")
        return

    user = await get_user(message.from_user.id)
    if not user:
        await state.clear()
        return

    tz = _tf.timezone_at(lat=user["lat"], lng=user["lon"]) or "UTC"
    await set_night_mode_time(message.from_user.id, night_start, night_end, tz)
    await state.clear()

    user = await get_user(message.from_user.id)
    await message.answer(
        f"Ночной режим: {night_start:02d}:00 - {night_end:02d}:00 ({tz}). Сохранено.",
        reply_markup=settings_keyboard(user),
    )


@router.callback_query(F.data.startswith("settings:toggle:"))
async def cb_toggle_track(callback: CallbackQuery) -> None:
    field = callback.data.removeprefix("settings:toggle:")
    user = await get_user(callback.from_user.id)
    if not user:
        await callback.answer("Сначала настрой бота через /start.")
        return

    new_val = not user.get(field, True)
    await set_user_track(callback.from_user.id, field, new_val)

    user = await get_user(callback.from_user.id)
    await callback.message.edit_text(settings_text(user), reply_markup=settings_keyboard(user))
    await callback.answer()


@router.callback_query(F.data == "settings:change_city")
async def cb_change_city(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(OnboardingStates.waiting_for_input)
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.message.answer(
        "Укажи новый город — напиши название или поделись геолокацией.",
        reply_markup=location_keyboard(),
    )
    await callback.answer()


@router.callback_query(F.data == "settings:noop")
async def cb_noop(callback: CallbackQuery) -> None:
    await callback.answer()


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
