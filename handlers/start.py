from aiogram import Router, F
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    Message,
    ReplyKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardRemove,
)
from air_api import waqi_client
from db import save_user

router = Router()

BTN_LOCATION = "📍 Поделиться геолокацией"
BTN_MANUAL = "✏️ Ввести город вручную"


class OnboardingStates(StatesGroup):
    waiting_for_input = State()


def location_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=BTN_LOCATION, request_location=True)],
            [KeyboardButton(text=BTN_MANUAL)],
        ],
        resize_keyboard=True,
        one_time_keyboard=True,
    )


@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext) -> None:
    await state.set_state(OnboardingStates.waiting_for_input)
    await message.answer(
        "Привет! Я слежу за качеством воздуха 🌬\n"
        "Укажи свой город — напиши название или поделись геолокацией.",
        reply_markup=location_keyboard(),
    )


@router.message(OnboardingStates.waiting_for_input, F.location)
async def handle_location(message: Message, state: FSMContext) -> None:
    lat = message.location.latitude
    lon = message.location.longitude
    await message.answer("Определяю твоё местоположение...", reply_markup=ReplyKeyboardRemove())

    result = await waqi_client.get_aqi_by_coords(lat, lon)
    if result is None:
        await message.answer(
            "Не удалось получить данные о качестве воздуха для твоей локации. "
            "Попробуй ввести город вручную.",
            reply_markup=location_keyboard(),
        )
        return

    city_name = result["city_name"]
    aqi = result["aqi"]

    await save_user(
        user_id=message.from_user.id,
        username=message.from_user.username,
        city_name=city_name,
        lat=lat,
        lon=lon,
    )
    await state.clear()
    await message.answer(
        f"Определил: {city_name}. AQI сейчас: {aqi}. Буду присылать алерты 👍"
    )


@router.message(OnboardingStates.waiting_for_input, F.text)
async def handle_city_text(message: Message, state: FSMContext) -> None:
    text = message.text.strip()
    if text in (BTN_MANUAL,):
        await message.answer(
            "Напиши название города (например: Moscow, Belgrade, Tokyo):",
            reply_markup=ReplyKeyboardRemove(),
        )
        return

    await message.answer("Ищу данные...", reply_markup=ReplyKeyboardRemove())
    result = await waqi_client.get_aqi_by_city(text)
    if result is None or result.get("lat") is None:
        await message.answer(
            "Не нашёл такой город, попробуй написать по-английски или уточни название.",
            reply_markup=location_keyboard(),
        )
        return

    city_name = result["city_name"]
    aqi = result["aqi"]
    lat = result["lat"]
    lon = result["lon"]

    await save_user(
        user_id=message.from_user.id,
        username=message.from_user.username,
        city_name=city_name,
        lat=lat,
        lon=lon,
    )
    await state.clear()
    await message.answer(
        f"Определил: {city_name}. AQI сейчас: {aqi}. Буду присылать алерты 👍"
    )
