import logging
from typing import Optional
import httpx

logger = logging.getLogger(__name__)

OPEN_METEO_BASE = "https://api.open-meteo.com/v1"

# WMO weather interpretation codes considered extreme
# 95: Thunderstorm, 96/99: Thunderstorm with hail
# 65/67: Heavy rain / heavy freezing rain
# 75/77: Heavy snowfall / snow grains
# 82: Violent rain showers
EXTREME_WEATHER_CODES = {65, 67, 75, 77, 82, 95, 96, 99}

# Wind speed threshold (km/h) for storm alert
STORM_WIND_KMH = 50.0


async def get_current_weather(lat: float, lon: float) -> Optional[dict]:
    """
    Return current weather conditions from Open-Meteo.

    Returns dict with keys:
      - weather_code (int): WMO code
      - wind_speed (float): km/h
      - is_extreme (bool): True if conditions are severe
    Returns None on error.
    """
    url = (
        f"{OPEN_METEO_BASE}/forecast"
        f"?latitude={lat}&longitude={lon}"
        f"&current=weather_code,wind_speed_10m"
    )
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            data = resp.json()

        current = data.get("current", {})
        weather_code = current.get("weather_code")
        wind_speed = current.get("wind_speed_10m")

        if weather_code is None or wind_speed is None:
            return None

        is_extreme = (
            int(weather_code) in EXTREME_WEATHER_CODES
            or float(wind_speed) >= STORM_WIND_KMH
        )
        return {
            "weather_code": int(weather_code),
            "wind_speed": float(wind_speed),
            "is_extreme": is_extreme,
        }
    except Exception as exc:
        logger.warning("Open-Meteo weather request failed: %s", exc)
        return None
