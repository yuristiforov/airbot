import logging
from typing import Optional
import httpx
from config import settings

logger = logging.getLogger(__name__)

WAQI_BASE = "https://api.waqi.info"


class WaqiClient:
    def __init__(self) -> None:
        self._token = settings.WAQI_TOKEN
        self._client = httpx.AsyncClient(timeout=10.0)

    async def _get(self, url: str) -> Optional[dict]:
        try:
            resp = await self._client.get(url)
            resp.raise_for_status()
            data = resp.json()
            if data.get("status") != "ok":
                return None
            return data.get("data")
        except Exception as exc:
            logger.warning("WAQI request failed: %s", exc)
            return None

    async def get_aqi_by_coords(self, lat: float, lon: float) -> Optional[dict]:
        url = f"{WAQI_BASE}/feed/geo:{lat};{lon}/?token={self._token}"
        data = await self._get(url)
        if data is None:
            return None
        aqi = data.get("aqi")
        if aqi == "-" or aqi is None:
            return None
        city_name = (
            data.get("city", {}).get("name")
            or data.get("city", {}).get("url", "").split("/")[-1]
            or f"{lat:.2f},{lon:.2f}"
        )
        return {"aqi": int(aqi), "city_name": city_name}

    async def get_aqi_by_city(self, city_name: str) -> Optional[dict]:
        url = f"{WAQI_BASE}/feed/{city_name}/?token={self._token}"
        data = await self._get(url)
        if data is None:
            return None
        aqi = data.get("aqi")
        if aqi == "-" or aqi is None:
            return None
        city_info = data.get("city", {})
        resolved_name = city_info.get("name") or city_name
        geo = city_info.get("geo", [None, None])
        lat = geo[0] if geo and len(geo) >= 2 else None
        lon = geo[1] if geo and len(geo) >= 2 else None
        return {
            "aqi": int(aqi),
            "city_name": resolved_name,
            "lat": lat,
            "lon": lon,
        }

    async def close(self) -> None:
        await self._client.aclose()


waqi_client = WaqiClient()
