import logging
from datetime import datetime

from aiogram import Router, types, F
from aiogram.filters import Command
from sqlalchemy import select, func

from bot.database import async_session
from bot.keyboards import main_menu_keyboard
from bot.models import Meal, Subscription, User
from bot.services.subscription import check_access

router = Router()
logger = logging.getLogger(__name__)


@router.message(Command("profile"))
async def cmd_profile(message: types.Message) -> None:
    async with async_session() as session:
        user_result = await session.execute(select(User).where(User.id == message.from_user.id))
        user = user_result.scalar_one_or_none()
        if not user:
            await message.answer("Вы не зарегистрированы. Нажмите /start")
            return

        meal_count = await session.execute(
            select(func.count()).select_from(Meal).where(Meal.user_id == message.from_user.id)
        )
        total_meals = meal_count.scalar() or 0

        sub_result = await session.execute(
            select(Subscription)
            .where(Subscription.user_id == message.from_user.id, Subscription.is_active.is_(True))
            .order_by(Subscription.end_date.desc())
            .limit(1)
        )
        sub = sub_result.scalar_one_or_none()

    status_text = ""
    if user.access_status == "trial" and user.trial_end and user.trial_end > datetime.utcnow():
        days = (user.trial_end - datetime.utcnow()).days
        status_text = f"🎁 Пробный доступ ({days} дн.)"
    elif sub and sub.end_date > datetime.utcnow():
        days = (sub.end_date - datetime.utcnow()).days
        status_text = f"✅ Подписка до {sub.end_date.strftime('%d.%m.%Y')} ({days} дн.)"
    else:
        status_text = "❌ Нет активной подписки"

    text = (
        f"👤 Профиль\n\n"
        f"Имя: {user.first_name or '—'}\n"
        f"Username: @{user.username or '—'}\n"
        f"Дата регистрации: {user.registered_at.strftime('%d.%m.%Y')}\n"
        f"Статус: {status_text}\n"
        f"Всего анализов: {total_meals}"
    )
    await message.answer(text)


@router.message(F.text == "👤 Профиль")
async def btn_profile(message: types.Message) -> None:
    await cmd_profile(message)
