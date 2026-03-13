from aiogram import Router, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    Message,
    CallbackQuery,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)
from db import get_user, set_user_active, set_user_track
from air_api import waqi_client
from handlers.start import OnboardingStates, location_keyboard

router = Router()


def _track_row(label: str, enabled: bool, callback: str) -> list[InlineKeyboardButton]:
    toggle = InlineKeyboardButton(
        text="✅ Вкл" if enabled else "❌ Выкл",
        callback_data=callback,
    )
    return [InlineKeyboardButton(text=label, callback_data="settings:noop"), toggle]


def settings_keyboard(user: dict) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
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
    ])


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
