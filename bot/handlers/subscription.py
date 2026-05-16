import logging
from datetime import datetime

from aiogram import Router, types, F
from aiogram.filters import Command
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from sqlalchemy import select

from bot.config import settings
from bot.database import async_session
from bot.keyboards import main_menu_keyboard, subscription_keyboard
from bot.models import Payment, Subscription, User
from bot.services.subscription import check_access, activate_subscription

router = Router()
logger = logging.getLogger(__name__)


@router.message(Command("subscribe"))
async def cmd_subscribe(message: types.Message) -> None:
    async with async_session() as session:
        has_access = await check_access(session, message.from_user.id)

    if has_access:
        await message.answer("У вас уже есть активная подписка! ✅")
        return

    await message.answer(
        "Выберите тариф подписки:",
        reply_markup=subscription_keyboard(),
    )


@router.message(F.text == "💳 Подписка")
async def btn_subscribe(message: types.Message) -> None:
    await cmd_subscribe(message)


@router.callback_query(F.data == "sub_1m")
async def sub_1m(callback: types.CallbackQuery) -> None:
    await callback.answer()
    await _create_yookassa_payment(
        callback.from_user.id, "1m", "Подписка на 1 месяц",
        settings.MONTH_PRICE / 100, 30,
    )


@router.callback_query(F.data == "sub_3m")
async def sub_3m(callback: types.CallbackQuery) -> None:
    await callback.answer()
    await _create_yookassa_payment(
        callback.from_user.id, "3m", "Подписка на 3 месяца",
        settings.THREE_MONTHS_PRICE / 100, 90,
    )


async def _create_yookassa_payment(
    user_id: int, sub_type: str, description: str, amount_rub: float, days: int,
) -> None:
    from bot.services.yookassa import create_payment

    result = await create_payment(
        user_id=user_id,
        sub_type=sub_type,
        amount_rub=amount_rub,
        description=description,
    )

    bot = __import__("aiogram").Bot.get_current()

    if not result:
        await bot.send_message(
            user_id,
            "❌ Не удалось создать платёж. Попробуйте позже или обратитесь в поддержку.",
        )
        return

    async with async_session() as session:
        payment = Payment(
            user_id=user_id,
            amount=int(amount_rub * 100),
            currency="RUB",
            sub_type=sub_type,
            telegram_payment_id=result["payment_id"],
            status="pending",
        )
        session.add(payment)
        await session.commit()

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💳 Оплатить", url=result["confirmation_url"])],
        [InlineKeyboardButton(text="✅ Проверить оплату", callback_data=f"paycheck_{result['payment_id']}")],
    ])

    await bot.send_message(
        user_id,
        f"📋 <b>{description}</b>\n\n"
        f"Сумма: {amount_rub:.0f} ₽\n\n"
        f"Нажмите кнопку ниже для перехода к оплате.\n"
        f"После оплаты нажмите «Проверить оплату».",
        reply_markup=kb,
        parse_mode="HTML",
    )


@router.callback_query(F.data.startswith("paycheck_"))
async def check_payment(callback: types.CallbackQuery) -> None:
    await callback.answer()
    payment_id = callback.data.removeprefix("paycheck_")

    from bot.services.yookassa import get_payment_info

    info = await get_payment_info(payment_id)
    if not info:
        await callback.message.answer("Не удалось проверить статус платежа. Попробуйте позже.")
        return

    if info.get("status") == "succeeded" and info.get("paid"):
        metadata = info.get("metadata", {})
        user_id = int(metadata.get("user_id", 0))
        sub_type = metadata.get("sub_type", "")

        if user_id != callback.from_user.id:
            await callback.message.answer("Ошибка: платёж не ваш.")
            return

        duration_days = 30 if sub_type == "1m" else 90

        async with async_session() as session:
            result = await session.execute(
                select(Payment).where(Payment.telegram_payment_id == payment_id)
            )
            payment = result.scalar_one_or_none()
            if payment and payment.status != "success":
                payment.status = "success"
                await activate_subscription(session, user_id, sub_type, duration_days)

        await callback.message.answer(
            "✅ Оплата прошла успешно! Подписка активирована.\n\n"
            "📸 Теперь вы можете отправлять фото еды для анализа.",
            reply_markup=main_menu_keyboard(),
        )
    elif info.get("status") == "canceled":
        await callback.message.answer("❌ Платёж отменён.")
    else:
        await callback.message.answer(
            "⏳ Платёж ещё не завершён. Нажмите «Проверить оплату» после оплаты."
        )


@router.callback_query(F.data == "sub_check")
async def sub_check(callback: types.CallbackQuery) -> None:
    await callback.answer()
    async with async_session() as session:
        result = await session.execute(
            select(Subscription)
            .where(Subscription.user_id == callback.from_user.id, Subscription.is_active.is_(True))
            .order_by(Subscription.end_date.desc())
            .limit(1)
        )
        sub = result.scalar_one_or_none()
        user_result = await session.execute(select(User).where(User.id == callback.from_user.id))
        user = user_result.scalar_one_or_none()

    if sub and sub.end_date > datetime.utcnow():
        days_left = (sub.end_date - datetime.utcnow()).days
        await callback.message.answer(f"✅ Подписка активна до {sub.end_date.strftime('%d.%m.%Y')} (осталось {days_left} дн.)")
    elif user and user.access_status == "trial" and user.trial_end and user.trial_end > datetime.utcnow():
        days_left = (user.trial_end - datetime.utcnow()).days
        await callback.message.answer(f"🎁 Пробный доступ: осталось {days_left} дн.")
    else:
        await callback.message.answer("❌ Активной подписки нет.", reply_markup=subscription_keyboard())


@router.callback_query(F.data == "help")
async def callback_help(callback: types.CallbackQuery) -> None:
    await callback.answer()
    text = (
        "📸 Как пользоваться:\n\n"
        "1. Отправьте фото блюда\n"
        "2. Бот определит еду и рассчитает КБЖУ, ХЕ и БЖЕ\n"
        "3. Через 2 часа придёт напоминание\n\n"
        "⚠️ Данные приблизительные. Бот не является медицинским сервисом."
    )
    await callback.message.answer(text)
