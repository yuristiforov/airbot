# AirQuality Telegram Bot — Project Context

## What this bot does
A Telegram bot that monitors air quality (AQI/PM2.5) for each user's location and sends
alerts when air quality crosses dangerous thresholds. Multi-user: every user has their own
city, settings, and independent alert state.

---

## Stack
- **Python 3.11+**
- **aiogram 3.x** — Telegram Bot framework (async, FSM built-in)
- **APScheduler 3.x** — in-process async scheduler (hourly AQI checks)
- **SQLite + aiosqlite** — persistent storage, one file, zero infra
- **httpx** — async HTTP client for WAQI API
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
├── alerts.py               # alert state machine: check_and_notify(user, aqi)
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
    user_id     INTEGER PRIMARY KEY,
    username    TEXT,
    city_name   TEXT,           -- display name, e.g. "Belgrade"
    lat         REAL,
    lon         REAL,
    alert_100   BOOLEAN DEFAULT TRUE,   -- send warning at AQI >= 100
    alert_150   BOOLEAN DEFAULT TRUE,   -- send danger at AQI >= 150
    active      BOOLEAN DEFAULT TRUE,   -- user can pause alerts with /stop
    created_at  DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at  DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS alert_state (
    user_id     INTEGER PRIMARY KEY REFERENCES users(user_id),
    last_aqi    INTEGER,
    last_status TEXT,           -- NULL | 'warning' | 'danger' | 'clear'
    checked_at  DATETIME
);
```

---

## Alert logic (alerts.py)

State machine — only send message on **state change**, never spam:

```
AQI >= 150  AND prev != 'danger'   → send DANGER alert, set state='danger'
AQI >= 100  AND prev not in (warning, danger) → send WARNING alert, set state='warning'  
AQI < 100   AND prev in (warning, danger)     → send ALL-CLEAR, set state='clear'
otherwise   → do nothing
```

Alert messages (no parse_mode — plain text only to avoid escaping issues):
- WARNING  (AQI 100–149): "⚠️ Воздух грязный (AQI {aqi}). Лишний раз не выходи из дома."
- DANGER   (AQI 150+):    "🚨 Опасно! AQI {aqi}. Сиди дома, закрой окна и вентиляцию."
- ALL-CLEAR (AQI < 100):  "✅ Воздух улучшился (AQI {aqi}). Опасность отменена."

---

## WAQI API

Base URL: `https://api.waqi.info`
Token: from env `WAQI_TOKEN`

Endpoints used:
- By coordinates: `GET /feed/geo:{lat};{lon}/?token={TOKEN}`
- By city name:   `GET /feed/{city}/?token={TOKEN}`

Response field: `data.aqi` (integer, US AQI scale)
If `data.aqi == "-"` — station has no data, skip silently.

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
- `/settings` — show current city + toggle alerts on/off
- `/stop` — pause all alerts (sets active=False)
- `/resume` — resume alerts

---

## Scheduler (scheduler.py)

- APScheduler `AsyncIOScheduler` with `IntervalTrigger(hours=1)`
- On each tick: `SELECT * FROM users WHERE active=1`
- For each user: fetch AQI → run alert state machine → update `alert_state`
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

---

## Key implementation notes

1. **No parse_mode anywhere** — use plain text in all bot.send_message calls to avoid MarkdownV2 escaping crashes
2. **FSM storage** — use `FSMContext` with `MemoryStorage` (single process, restarts are rare; can upgrade to FileStorage if needed)
3. **aiosqlite** — all DB calls must be async, use `async with aiosqlite.connect(DB_PATH) as db`
4. **Graceful shutdown** — stop scheduler before bot polling stops
5. **WAQI rate limits** — 1000 req/day free; with 50 users = 1200 req/day → consider caching last result per city for 55 min to stay within limits
6. **City deduplication (optional optimization)** — group users by (lat,lon) rounded to 2 decimal places and make one API call per unique location per hour

---

## What NOT to do
- Do not use Redis — SQLite is enough
- Do not use webhooks — polling is fine for this scale
- Do not use parse_mode=MarkdownV2 anywhere
- Do not try to get user IP — Telegram doesn't expose it
