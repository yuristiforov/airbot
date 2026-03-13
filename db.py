import aiosqlite
from typing import Optional
from config import settings

DB_PATH = settings.db_path


async def _add_column_if_missing(db, table: str, column: str, definition: str) -> None:
    async with db.execute(f"PRAGMA table_info({table})") as cursor:
        cols = await cursor.fetchall()
    if not any(col[1] == column for col in cols):
        await db.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")


async def init_db() -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id     INTEGER PRIMARY KEY,
                username    TEXT,
                city_name   TEXT,
                lat         REAL,
                lon         REAL,
                alert_100   BOOLEAN DEFAULT TRUE,
                alert_150   BOOLEAN DEFAULT TRUE,
                active      BOOLEAN DEFAULT TRUE,
                track_air   BOOLEAN DEFAULT TRUE,
                track_uv    BOOLEAN DEFAULT TRUE,
                track_weather BOOLEAN DEFAULT TRUE,
                created_at  DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at  DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS alert_state (
                user_id         INTEGER PRIMARY KEY REFERENCES users(user_id),
                last_aqi        INTEGER,
                last_status     TEXT,
                uv_status       TEXT,
                last_uv         REAL,
                weather_status  TEXT,
                last_weather_code INTEGER,
                checked_at      DATETIME
            )
        """)
        # Migrate existing installations
        for col, defn in [
            ("track_air",    "BOOLEAN DEFAULT TRUE"),
            ("track_uv",     "BOOLEAN DEFAULT TRUE"),
            ("track_weather","BOOLEAN DEFAULT TRUE"),
        ]:
            await _add_column_if_missing(db, "users", col, defn)
        for col, defn in [
            ("uv_status",          "TEXT"),
            ("last_uv",            "REAL"),
            ("weather_status",     "TEXT"),
            ("last_weather_code",  "INTEGER"),
        ]:
            await _add_column_if_missing(db, "alert_state", col, defn)
        await db.commit()


async def get_user(user_id: int) -> Optional[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM users WHERE user_id = ?", (user_id,)
        ) as cursor:
            row = await cursor.fetchone()
            return dict(row) if row else None


async def save_user(
    user_id: int,
    username: Optional[str],
    city_name: str,
    lat: float,
    lon: float,
) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            INSERT INTO users (user_id, username, city_name, lat, lon)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                username  = excluded.username,
                city_name = excluded.city_name,
                lat       = excluded.lat,
                lon       = excluded.lon,
                active    = TRUE,
                updated_at = CURRENT_TIMESTAMP
        """, (user_id, username, city_name, lat, lon))
        await db.execute("""
            INSERT INTO alert_state (user_id, last_aqi, last_status, checked_at)
            VALUES (?, NULL, NULL, NULL)
            ON CONFLICT(user_id) DO NOTHING
        """, (user_id,))
        await db.commit()


async def update_user_location(
    user_id: int,
    city_name: str,
    lat: float,
    lon: float,
) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            UPDATE users
            SET city_name = ?, lat = ?, lon = ?, updated_at = CURRENT_TIMESTAMP
            WHERE user_id = ?
        """, (city_name, lat, lon, user_id))
        await db.commit()


async def set_user_active(user_id: int, active: bool) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE users SET active = ?, updated_at = CURRENT_TIMESTAMP WHERE user_id = ?",
            (active, user_id),
        )
        await db.commit()


async def set_user_alert(user_id: int, field: str, value: bool) -> None:
    allowed = {"alert_100", "alert_150"}
    if field not in allowed:
        raise ValueError(f"Unknown alert field: {field}")
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            f"UPDATE users SET {field} = ?, updated_at = CURRENT_TIMESTAMP WHERE user_id = ?",
            (value, user_id),
        )
        await db.commit()


async def set_user_track(user_id: int, field: str, value: bool) -> None:
    allowed = {"track_air", "track_uv", "track_weather"}
    if field not in allowed:
        raise ValueError(f"Unknown track field: {field}")
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            f"UPDATE users SET {field} = ?, updated_at = CURRENT_TIMESTAMP WHERE user_id = ?",
            (value, user_id),
        )
        await db.commit()


async def get_all_active_users() -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM users WHERE active = TRUE AND lat IS NOT NULL"
        ) as cursor:
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]


async def get_alert_state(user_id: int) -> Optional[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM alert_state WHERE user_id = ?", (user_id,)
        ) as cursor:
            row = await cursor.fetchone()
            return dict(row) if row else None


async def update_alert_state(user_id: int, aqi: int, status: str) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            INSERT INTO alert_state (user_id, last_aqi, last_status, checked_at)
            VALUES (?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(user_id) DO UPDATE SET
                last_aqi    = excluded.last_aqi,
                last_status = excluded.last_status,
                checked_at  = excluded.checked_at
        """, (user_id, aqi, status))
        await db.commit()


async def update_uv_alert_state(user_id: int, uv: float, status: str) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            INSERT INTO alert_state (user_id, uv_status, last_uv, checked_at)
            VALUES (?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(user_id) DO UPDATE SET
                uv_status  = excluded.uv_status,
                last_uv    = excluded.last_uv,
                checked_at = excluded.checked_at
        """, (user_id, status, uv))
        await db.commit()


async def update_weather_alert_state(user_id: int, weather_code: int, status: str) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            INSERT INTO alert_state (user_id, weather_status, last_weather_code, checked_at)
            VALUES (?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(user_id) DO UPDATE SET
                weather_status     = excluded.weather_status,
                last_weather_code  = excluded.last_weather_code,
                checked_at         = excluded.checked_at
        """, (user_id, status, weather_code))
        await db.commit()
