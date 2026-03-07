from aiogram import Router, F
from aiogram.types import Message
from db import get_user, update_user_location
from air_api import waqi_client

router = Router()


@router.message(F.location)
async def handle_location_update(message: Message) -> None:
    user = await get_user(message.from_user.id)
    if not user:
        await message.answer("Используй /start для начала работы.")
        return

    lat = message.location.latitude
    lon = message.location.longitude
    result = await waqi_client.get_aqi_by_coords(lat, lon)
    if result is None:
        await message.answer("Не удалось получить данные о качестве воздуха для этой локации.")
        return

    city_name = result["city_name"]
    await update_user_location(message.from_user.id, city_name, lat, lon)
    await message.answer(
        f"Локация обновлена: {city_name}. AQI сейчас: {result['aqi']}."
    )
