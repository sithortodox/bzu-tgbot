import logging

from aiogram import Router, types
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext

from bot.database import async_session
from bot.keyboards import main_menu_keyboard, subscription_keyboard
from bot.services.subscription import register_user, check_access

router = Router()
logger = logging.getLogger(__name__)

DISCLAIMER = "\n\n⚠️ Данные приблизительные. Бот не является медицинским сервисом и не заменяет консультацию врача."


@router.message(CommandStart())
async def cmd_start(message: types.Message, state: FSMContext) -> None:
    await state.clear()
    async with async_session() as session:
        user = await register_user(session, message.from_user.id, message.from_user.username, message.from_user.first_name)
        has_access = await check_access(session, message.from_user.id)

    if user.access_status == "trial" and has_access:
        days_left = (user.trial_end - __import__("datetime").datetime.utcnow()).days
        text = (
            f"Привет, {message.from_user.first_name}! 👋\n\n"
            f"Я бот для расчёта пищевой ценности по фото еды.\n"
            f"📸 Отправь мне фото блюда — и я рассчитаю КБЖУ, ХЕ и БЖЕ.\n\n"
            f"🎁 Пробный доступ: {days_left} дн.\n"
            f"{DISCLAIMER}"
        )
    elif has_access:
        text = (
            f"С возвращением, {message.from_user.first_name}! 👋\n\n"
            f"📸 Отправь фото еды для анализа.\n"
            f"{DISCLAIMER}"
        )
    else:
        text = (
            f"Привет, {message.from_user.first_name}! 👋\n\n"
            f"Пробный доступ истёк. Для продолжения оформите подписку.\n"
            f"{DISCLAIMER}"
        )
        await message.answer(text, reply_markup=subscription_keyboard())
        return

    await message.answer(text, reply_markup=main_menu_keyboard())


@router.message(lambda m: m.text == "❓ Помощь")
async def cmd_help(message: types.Message) -> None:
    text = (
        "📸 Как пользоваться ботом:\n\n"
        "1. Отправьте фото блюда\n"
        "2. Бот определит еду и рассчитает КБЖУ, ХЕ и БЖЕ\n"
        "3. Через 2 часа придёт напоминание\n\n"
        "📋 Команды:\n"
        "/start — приветствие\n"
        "/profile — ваш профиль\n"
        "/history — история приёмов\n"
        "/subscribe — подписка\n\n"
        f"{DISCLAIMER}"
    )
    await message.answer(text)
