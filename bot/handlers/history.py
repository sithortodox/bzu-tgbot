import logging

from aiogram import Router, types, F
from aiogram.filters import Command
from sqlalchemy import select

from bot.database import async_session
from bot.models import Meal

router = Router()
logger = logging.getLogger(__name__)


@router.message(Command("history"))
async def cmd_history(message: types.Message) -> None:
    async with async_session() as session:
        result = await session.execute(
            select(Meal)
            .where(Meal.user_id == message.from_user.id)
            .order_by(Meal.created_at.desc())
            .limit(5)
        )
        meals = result.scalars().all()

    if not meals:
        await message.answer("📭 История пуста. Отправьте фото еды для первого анализа!")
        return

    text = "📋 Последние приёмы пищи:\n\n"
    for i, meal in enumerate(meals, 1):
        text += f"{i}. <b>{meal.dish_name}</b>\n"
        text += f"   📅 {meal.created_at.strftime('%d.%m.%Y %H:%M')}\n"
        if meal.calories is not None:
            text += f"   🔥 {int(meal.calories)} ккал"
        if meal.xe is not None:
            text += f" | 🥖 ХЕ: {meal.xe}"
        if meal.bje is not None:
            text += f" | 💉 БЖЕ: {meal.bje}"
        text += "\n\n"

    await message.answer(text, parse_mode="HTML")


@router.message(F.text == "📋 История")
async def btn_history(message: types.Message) -> None:
    await cmd_history(message)


@router.callback_query(F.data == "history_5")
async def callback_history_5(callback: types.CallbackQuery) -> None:
    await callback.answer()
    async with async_session() as session:
        result = await session.execute(
            select(Meal)
            .where(Meal.user_id == callback.from_user.id)
            .order_by(Meal.created_at.desc())
            .limit(5)
        )
        meals = result.scalars().all()

    if not meals:
        await callback.message.answer("📭 История пуста.")
        return

    text = "📋 Последние 5 приёмов:\n\n"
    for i, meal in enumerate(meals, 1):
        text += f"{i}. <b>{meal.dish_name}</b>\n"
        text += f"   📅 {meal.created_at.strftime('%d.%m.%Y %H:%M')}\n"
        if meal.calories is not None:
            text += f"   🔥 {int(meal.calories)} ккал"
        if meal.xe is not None:
            text += f" | 🥖 ХЕ: {meal.xe}"
        if meal.bje is not None:
            text += f" | 💉 БЖЕ: {meal.bje}"
        text += "\n\n"

    await callback.message.answer(text, parse_mode="HTML")
