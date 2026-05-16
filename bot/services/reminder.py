import logging
from datetime import datetime, timedelta

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from aiogram import Bot
from aiogram.exceptions import TelegramForbiddenError

from bot.database import async_session
from bot.models import Meal, Reminder

logger = logging.getLogger(__name__)

scheduler = AsyncIOScheduler()

REMINDER_HOURS = 2


async def schedule_reminder(bot: Bot, session: AsyncSession, user_id: int, meal_id: int) -> None:
    scheduled_at = datetime.utcnow() + timedelta(hours=REMINDER_HOURS)

    reminder = Reminder(
        user_id=user_id,
        meal_id=meal_id,
        scheduled_at=scheduled_at,
        status="pending",
    )
    session.add(reminder)
    await session.commit()
    await session.refresh(reminder)

    scheduler.add_job(
        _send_reminder,
        "date",
        run_date=scheduled_at,
        args=[bot, reminder.id],
        id=f"reminder_{reminder.id}",
        replace_existing=False,
    )
    logger.info("Reminder scheduled: user=%d meal=%d at=%s", user_id, meal_id, scheduled_at)


async def _send_reminder(bot: Bot, reminder_id: int) -> None:
    async with async_session() as session:
        result = await session.execute(select(Reminder).where(Reminder.id == reminder_id))
        reminder = result.scalar_one_or_none()
        if not reminder or reminder.status != "pending":
            return

        meal_result = await session.execute(select(Meal).where(Meal.id == reminder.meal_id))
        meal = meal_result.scalar_one_or_none()

        text = "⏰ Напоминание: прошло 2 часа после приёма пищи"
        if meal:
            text += f"\n🍽 Блюдо: {meal.dish_name}"
            if meal.xe is not None:
                text += f"\n🥖 ХЕ: {meal.xe}"
            if meal.bje is not None:
                text += f"\n🧈 БЖЕ: {meal.bje}"
        text += "\n\nДанные приблизительные. При необходимости измерьте сахар и проконсультируйтесь с врачом."

        try:
            await bot.send_message(chat_id=reminder.user_id, text=text)
            reminder.status = "sent"
            reminder.sent_at = datetime.utcnow()
        except TelegramForbiddenError:
            logger.warning("User %d blocked the bot, reminder not sent", reminder.user_id)
            reminder.status = "failed"
        except Exception as e:
            logger.error("Reminder send error: %s", e)
            reminder.status = "failed"

        await session.commit()


def start_scheduler() -> None:
    if not scheduler.running:
        scheduler.start()
        logger.info("APScheduler started")


def shutdown_scheduler() -> None:
    if scheduler.running:
        scheduler.shutdown()
        logger.info("APScheduler shutdown")
