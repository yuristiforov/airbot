# AirQuality Telegram Bot — Project Context

## What this bot does
A Telegram bot that monitors air quality (AQI/PM2.5), UV index, and extreme weather
for each user's location and sends alerts when conditions cross dangerous thresholds.
Multi-user: every user has their own city, settings, and independent alert state.

---

## Stack
- **Python 3.11+**
- **aiogram 3.x** — Telegram Bot framework (async, FSM built-in)
- **APScheduler 3.x** — in-process async scheduler (hourly checks)
- **SQLite + aiosqlite** — persistent storage, one file, zero infra
- **httpx** — async HTTP client for WAQI and Open-Meteo APIs
- **Docker Compose** — single container deployment on Hetzner VPS

---

## Project structure
```
airbot/
├── CLAUDE.md
├── docker-compose.yml
├── Dockerfile
├── requirements.txt
├── .env.example
├── bot.py                  # entry point: init bot, dispatcher, scheduler
├── config.py               # pydantic-settings, reads from .env
├── db.py                   # aiosqlite: init schema, CRUD helpers
├── air_api.py              # WAQI API client (get_aqi_by_coords, get_aqi_by_city)
├── uv_api.py               # Open-Meteo UV index client (get_uv_index)
├── weather_api.py          # Open-Meteo extreme weather client (get_current_weather)
├── alerts.py               # alert state machines: air, UV, weather
├── scheduler.py            # APScheduler setup, hourly_check job
├── handlers/
│   ├── __init__.py
│   ├── start.py            # /start, onboarding FSM
│   ├── settings.py         # /settings, /status, /stop commands
│   └── location.py         # handles MessageType.LOCATION and city text input
└── data/
    └── airbot.db           # SQLite file (gitignored, mounted as Docker volume)
```

---

## Database schema

```sql
CREATE TABLE IF NOT EXISTS users (
    user_id       INTEGER PRIMARY KEY,
    username      TEXT,
    city_name     TEXT,           -- display name, e.g. "Belgrade"
    lat           REAL,
    lon           REAL,
    alert_100     BOOLEAN DEFAULT TRUE,   -- send warning at AQI >= 100
    alert_150     BOOLEAN DEFAULT TRUE,   -- send danger at AQI >= 150
    active        BOOLEAN DEFAULT TRUE,   -- user can pause alerts with /stop
    track_air     BOOLEAN DEFAULT TRUE,   -- enable air quality alerts
    track_uv      BOOLEAN DEFAULT TRUE,   -- enable UV index alerts
    track_weather BOOLEAN DEFAULT TRUE,   -- enable extreme weather alerts
    created_at    DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at    DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS alert_state (
    user_id            INTEGER PRIMARY KEY REFERENCES users(user_id),
    last_aqi           INTEGER,
    last_status        TEXT,           -- NULL | 'warning' | 'danger' | 'clear'
    uv_status          TEXT,           -- NULL | 'high' | 'extreme' | 'safe'
    last_uv            REAL,
    weather_status     TEXT,           -- NULL | 'alert' | 'clear'
    last_weather_code  INTEGER,
    checked_at         DATETIME
);
```

Migration: `init_db()` uses `PRAGMA table_info` to add new columns on existing DBs without
dropping data.

---

## Alert logic (alerts.py)

### Air quality — `check_and_notify()`
State machine — only send on **state change**:
```
AQI >= 150  AND prev != 'danger'              → DANGER,  state='danger'
AQI >= 100  AND prev not in (warning, danger) → WARNING, state='warning'
AQI < 100   AND prev in (warning, danger)     → CLEAR,   state='clear'
```

### UV index — `check_and_notify_uv()`
```
UV >= 11  AND prev != 'extreme'          → EXTREME alert, state='extreme'
UV >= 6   AND prev not in (high,extreme) → HIGH alert,    state='high'
UV < 6    AND prev in (high,extreme)
          AND daytime (UTC 6–20)         → CLEAR alert,   state='safe'
UV < 6    AND nighttime                  → silently set   state='safe'
```
Night clear is suppressed to avoid daily noise (UV is always 0 at night).

### Extreme weather — `check_and_notify_weather()`
```
is_extreme AND prev != 'alert' → STORM alert, state='alert'
not extreme AND prev == 'alert' → CLEAR,      state='clear'
```
`is_extreme` = `wind_speed >= 50 km/h` OR `weather_code in {65,67,75,77,82,95,96,99}`

Alert messages — plain text only (no parse_mode):
- AIR WARNING  (AQI 100–149): "⚠️ Воздух грязный (AQI {aqi}). Лишний раз не выходи из дома."
- AIR DANGER   (AQI 150+):    "🚨 Опасно! AQI {aqi}. Сиди дома, закрой окна и вентиляцию."
- AIR CLEAR    (AQI < 100):   "✅ Воздух улучшился (AQI {aqi}). Опасность отменена."
- UV HIGH      (UV 6–10):     "☀️ Высокий UV-индекс ({uv}). Надень солнцезащитный крем."
- UV EXTREME   (UV 11+):      "🔆 Экстремальный UV-индекс ({uv})! Не выходи без защиты кожи и глаз."
- UV CLEAR:                   "☁️ UV-индекс нормализовался ({uv}). Можно выходить без крема."
- WEATHER ALERT:              "⛈ Экстремальная погода! Ветер {wind} км/ч, код погоды: {code}. Будь осторожен."
- WEATHER CLEAR:              "🌤 Экстремальная погода миновала. Условия нормализовались."

---

## APIs

### WAQI (air quality)
Base URL: `https://api.waqi.info`
Token: from env `WAQI_TOKEN`
- By coordinates: `GET /feed/geo:{lat};{lon}/?token={TOKEN}`
- By city name:   `GET /feed/{city}/?token={TOKEN}`
Response field: `data.aqi`; skip silently if `"-"` or null.

### Open-Meteo (UV + weather) — **no token required**
Base URL: `https://api.open-meteo.com/v1`
- UV index:   `GET /forecast?latitude={lat}&longitude={lon}&hourly=uv_index&timezone=UTC&forecast_days=1`
  → match current UTC hour in `hourly.time[]` array
- Weather:    `GET /forecast?latitude={lat}&longitude={lon}&current=weather_code,wind_speed_10m`
  → `current.weather_code`, `current.wind_speed_10m` (km/h)

---

## Onboarding flow (/start FSM)

```
/start
→ "Привет! Я слежу за качеством воздуха 🌬
   Укажи свой город — напиши название или поделись геолокацией."
→ Show reply keyboard:
   [📍 Поделиться геолокацией]
   [✏️ Ввести город вручную]

If location shared:
   → reverse geocode via WAQI (feed/geo:lat;lon) → get city name from response
   → confirm: "Определил: {city_name}. AQI сейчас: {aqi}. Буду присылать алерты 👍"
   → save user, schedule

If text entered:
   → query WAQI by city name
   → if found: confirm same as above
   → if not found: "Не нашёл такой город, попробуй написать по-английски или уточни название"
```

---

## Commands
- `/start` — onboarding or re-setup
- `/status` — current AQI for user's city
- `/settings` — show current city, alert toggles (air/UV/weather), active state
- `/stop` — pause all alerts (sets active=False)
- `/resume` — resume alerts

---

## Scheduler (scheduler.py)

- APScheduler `AsyncIOScheduler` with `IntervalTrigger(hours=1)`
- On each tick: `SELECT * FROM users WHERE active=1`
- For each user, independently (guarded by track_* flags):
  1. Fetch AQI via WAQI → run air alert state machine
  2. Fetch UV via Open-Meteo → run UV alert state machine
  3. Fetch weather via Open-Meteo → run weather alert state machine
- Run scheduler startup in `bot.py` on_startup hook

---

## Docker Compose

```yaml
services:
  airbot:
    build: .
    restart: unless-stopped
    env_file: .env
    volumes:
      - ./data:/app/data    # SQLite persistence
```

No Redis, no external DB, no nginx. Single container.

---

## Environment variables (.env.example)

```
BOT_TOKEN=your_telegram_bot_token
WAQI_TOKEN=your_waqi_api_token
DATA_DIR=/app/data
LOG_LEVEL=INFO
```

Open-Meteo requires no token.

---

## Key implementation notes

1. **No parse_mode anywhere** — use plain text in all bot.send_message calls to avoid MarkdownV2 escaping crashes
2. **FSM storage** — use `FSMContext` with `MemoryStorage` (single process, restarts are rare; can upgrade to FileStorage if needed)
3. **aiosqlite** — all DB calls must be async, use `async with aiosqlite.connect(DB_PATH) as db`
4. **Graceful shutdown** — stop scheduler before bot polling stops
5. **WAQI rate limits** — 1000 req/day free; with 50 users = 1200 req/day → consider caching last result per city for 55 min to stay within limits
6. **Open-Meteo rate limits** — free, no registration, generous limits; no caching needed for small user counts
7. **UV night suppression** — all-clear for UV is not sent if UTC hour is outside 6–20 to avoid daily midnight noise
8. **DB migration** — `init_db()` uses `PRAGMA table_info` + conditional `ALTER TABLE` to safely add new columns on existing installations without data loss

---

## What NOT to do
- Do not use Redis — SQLite is enough
- Do not use webhooks — polling is fine for this scale
- Do not use parse_mode=MarkdownV2 anywhere
- Do not try to get user IP — Telegram doesn't expose it
