import logging
from datetime import datetime

from aiogram import Router, types, F
from aiogram.filters import Command
from sqlalchemy import func, select

from bot.config import settings
from bot.database import async_session
from bot.keyboards import admin_keyboard
from bot.models import Meal, Payment, Subscription, User
from bot.services.subscription import grant_access

router = Router()
logger = logging.getLogger(__name__)


def is_admin(user_id: int) -> bool:
    return user_id in settings.ADMIN_IDS


@router.message(Command("admin"))
async def cmd_admin(message: types.Message) -> None:
    if not is_admin(message.from_user.id):
        return
    await message.answer("🛠 Админ-панель", reply_markup=admin_keyboard())


@router.callback_query(F.data == "admin_stats")
async def admin_stats(callback: types.CallbackQuery) -> None:
    if not is_admin(callback.from_user.id):
        await callback.answer("Нет доступа", show_alert=True)
        return
    await callback.answer()

    async with async_session() as session:
        total_users = (await session.execute(select(func.count()).select_from(User))).scalar() or 0
        active_subs = (
            await session.execute(
                select(func.count()).select_from(Subscription).where(Subscription.is_active.is_(True), Subscription.end_date > datetime.utcnow())
            )
        ).scalar() or 0
        total_meals = (await session.execute(select(func.count()).select_from(Meal))).scalar() or 0
        total_payments = (await session.execute(select(func.count()).select_from(Payment).where(Payment.status == "success"))).scalar() or 0

        trial_users = (await session.execute(select(func.count()).select_from(User).where(User.access_status == "trial"))).scalar() or 0
        expired_users = (await session.execute(select(func.count()).select_from(User).where(User.access_status == "expired"))).scalar() or 0

    text = (
        "📊 Статистика бота:\n\n"
        f"👥 Всего пользователей: {total_users}\n"
        f"🎁 Пробных: {trial_users}\n"
        f"✅ Активных подписок: {active_subs}\n"
        f"❌ Истёкших: {expired_users}\n"
        f"📸 Всего анализов: {total_meals}\n"
        f"💰 Успешных оплат: {total_payments}"
    )
    await callback.message.answer(text)


@router.callback_query(F.data == "admin_users")
async def admin_users(callback: types.CallbackQuery) -> None:
    if not is_admin(callback.from_user.id):
        await callback.answer("Нет доступа", show_alert=True)
        return
    await callback.answer()

    async with async_session() as session:
        result = await session.execute(select(User).order_by(User.registered_at.desc()).limit(10))
        users = result.scalars().all()

    if not users:
        await callback.message.answer("Пользователей нет.")
        return

    text = "👥 Последние 10 пользователей:\n\n"
    for u in users:
        status = u.access_status
        text += f"• {u.first_name or '—'} (@{u.username or '—'}) [{u.id}] — {status}\n"

    await callback.message.answer(text)


@router.message(Command("admin_grant"))
async def admin_grant(message: types.Message) -> None:
    if not is_admin(message.from_user.id):
        return

    parts = message.text.split()
    if len(parts) < 3:
        await message.answer("Формат: /admin_grant <user_id> <days>")
        return

    try:
        target_id = int(parts[1])
        days = int(parts[2])
    except ValueError:
        await message.answer("user_id и days должны быть числами.")
        return

    async with async_session() as session:
        user_result = await session.execute(select(User).where(User.id == target_id))
        user = user_result.scalar_one_or_none()
        if not user:
            await message.answer(f"Пользователь {target_id} не найден.")
            return
        await grant_access(session, target_id, days)

    await message.answer(f"✅ Доступ выдан пользователю {target_id} на {days} дней.")


@router.message(Command("admin_user"))
async def admin_user_info(message: types.Message) -> None:
    if not is_admin(message.from_user.id):
        return

    parts = message.text.split()
    if len(parts) < 2:
        await message.answer("Формат: /admin_user <user_id>")
        return

    try:
        target_id = int(parts[1])
    except ValueError:
        await message.answer("user_id должен быть числом.")
        return

    async with async_session() as session:
        user_result = await session.execute(select(User).where(User.id == target_id))
        user = user_result.scalar_one_or_none()
        if not user:
            await message.answer(f"Пользователь {target_id} не найден.")
            return

        meal_count = (await session.execute(select(func.count()).select_from(Meal).where(Meal.user_id == target_id))).scalar() or 0
        sub_result = await session.execute(
            select(Subscription).where(Subscription.user_id == target_id).order_by(Subscription.end_date.desc()).limit(1)
        )
        sub = sub_result.scalar_one_or_none()

    sub_text = f"до {sub.end_date.strftime('%d.%m.%Y')}" if sub and sub.end_date > datetime.utcnow() else "нет"
    text = (
        f"👤 Пользователь {target_id}\n\n"
        f"Имя: {user.first_name or '—'}\n"
        f"Username: @{user.username or '—'}\n"
        f"Регистрация: {user.registered_at.strftime('%d.%m.%Y')}\n"
        f"Статус: {user.access_status}\n"
        f"Подписка: {sub_text}\n"
        f"Анализов: {meal_count}"
    )
    await message.answer(text)
