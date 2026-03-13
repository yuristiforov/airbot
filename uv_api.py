import logging
from datetime import datetime, timezone
from typing import Optional
import httpx

logger = logging.getLogger(__name__)

OPEN_METEO_BASE = "https://api.open-meteo.com/v1"


async def get_uv_index(lat: float, lon: float) -> Optional[float]:
    """Return current UV index from Open-Meteo, or None if unavailable."""
    url = (
        f"{OPEN_METEO_BASE}/forecast"
        f"?latitude={lat}&longitude={lon}"
        f"&hourly=uv_index&timezone=UTC&forecast_days=1"
    )
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            data = resp.json()

        hourly = data.get("hourly", {})
        times = hourly.get("time", [])
        uv_values = hourly.get("uv_index", [])

        if not times or not uv_values:
            return None

        # Match current UTC hour: "YYYY-MM-DDTHH:00"
        current_hour_prefix = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:")
        for i, t in enumerate(times):
            if t.startswith(current_hour_prefix):
                val = uv_values[i]
                return float(val) if val is not None else None

        return None
    except Exception as exc:
        logger.warning("Open-Meteo UV request failed: %s", exc)
        return None
