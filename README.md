# BZUbot — Telegram-бот для расчёта пищевой ценности по фото еды

Бот анализирует фотографию блюда через ИИ и рассчитывает КБЖУ, хлебные единицы (ХЕ) и белково-жировые единицы (БЖЕ). Через 2 часа после приёма пищи отправляет напоминание.

## Функционал

- 📸 Анализ фото еды через ИИ (бесплатно, без API-ключей)
- 🔥 Расчёт калорий, белков, жиров, углеводов (КБЖУ)
- 🥖 Расчёт хлебных единиц (ХЕ = углеводы / 12)
- 💉 Расчёт белково-жировых единиц (БЖЕ = белки/2 + жиры/2)
- 📈 Гликемический индекс (ГИ)
- ⏰ Напоминание через 2 часа после приёма пищи
- 🎁 Пробный доступ — 2 дня при регистрации
- 💳 Подписка через Telegram Payments (1 мес — 499₽, 3 мес — 1290₽)
- 📋 История последних приёмов пищи
- 👤 Профиль пользователя
- 🛠 Админ-панель
- 🛡 Антиспам (5 фото/мин, 50 анализов/день)

## Технологии

- Python 3.11, aiogram 3
- PostgreSQL + SQLAlchemy + Alembic
- Redis (антиспам)
- APScheduler (напоминания)
- g4f.space API (бесплатный ИИ-анализ фото)
- Docker Compose

## Быстрый старт

```bash
# 1. Клонировать репозиторий
git clone https://github.com/sithortodox/bzu-tgbot.git
cd bzu-tgbot

# 2. Создать .env из примера
cp .env.example .env

# 3. Заполнить .env
# BOT_TOKEN — токен от @BotFather
# PROVIDER_TOKEN — токен для Telegram Payments (опционально)

# 4. Запустить
docker compose up --build -d
```

## Переменные окружения

| Переменная | Описание | По умолчанию |
|---|---|---|
| `BOT_TOKEN` | Токен Telegram бота | — |
| `DATABASE_URL` | URL PostgreSQL | `postgresql+psycopg2://bzubot:bzubot@localhost:5432/bzubot` |
| `REDIS_URL` | URL Redis | `redis://localhost:6379/0` |
| `ADMIN_IDS` | Telegram ID администраторов | `[]` |
| `MONTH_PRICE` | Цена 1 мес (копейки) | `49900` |
| `THREE_MONTHS_PRICE` | Цена 3 мес (копейки) | `129000` |
| `PROVIDER_TOKEN` | Токен Telegram Payments | — |

## Команды бота

| Команда | Описание |
|---|---|
| `/start` | Приветствие, регистрация |
| `/profile` | Профиль и статус подписки |
| `/history` | Последние 5 приёмов пищи |
| `/subscribe` | Оформить подписку |
| `/admin` | Админ-панель (только для ADMIN_IDS) |
| `/admin_grant <user_id> <days>` | Выдать доступ вручную |
| `/admin_user <user_id>` | Информация о пользователе |

## Структура проекта

```
bot/
├── config.py              — настройки из .env
├── database.py            — SQLAlchemy async engine
├── main.py                — entry point
├── keyboards.py           — inline/reply клавиатуры
├── handlers/
│   ├── start.py           — /start, регистрация, trial
│   ├── photo.py           — приём фото → AI → КБЖУ/ХЕ/БЖЕ
│   ├── subscription.py    — оплата, проверка подписки
│   ├── profile.py         — /profile
│   ├── history.py         — /history
│   ├── menu.py            — кнопки меню
│   └── admin.py           — админ-команды
├── models/
│   └── models.py          — User, Meal, Subscription, Payment, Reminder
└── services/
    ├── ai_analyzer.py     — ИИ-анализ фото (g4f.space)
    ├── calculator.py      — расчёт ХЕ, БЖЕ, ГИ
    ├── subscription.py    — логика подписок и trial
    ├── reminder.py        — APScheduler, напоминания через 2ч
    └── rate_limiter.py    — антиспам через Redis
```

## ИИ-анализ

Бот использует бесплатный API `g4f.space` на базе Pollinations AI. Никаких API-ключей не требуется. Фото сжимается до 512px перед отправкой для оптимизации скорости.

## Медицинский дисклеймер

Бот не является медицинским сервисом. Все расчёты приблизительные. В каждом ответе содержится предупреждение: «Данные приблизительные. Бот не является медицинским сервисом и не заменяет консультацию врача.»

## Лицензия

MIT
