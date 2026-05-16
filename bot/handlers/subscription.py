import logging
from datetime import datetime

from aiogram import Router, types, F
from aiogram.filters import Command
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
    await _send_invoice(callback.from_user.id, "1m", "Подписка на 1 месяц", settings.MONTH_PRICE, 30)


@router.callback_query(F.data == "sub_3m")
async def sub_3m(callback: types.CallbackQuery) -> None:
    await callback.answer()
    await _send_invoice(callback.from_user.id, "3m", "Подписка на 3 месяца", settings.THREE_MONTHS_PRICE, 90)


async def _send_invoice(user_id: int, sub_type: str, title: str, amount: int, days: int) -> None:
    from aiogram import Bot
    from aiogram.types import LabeledPrice

    bot = Bot.get_current()

    prices = [LabeledPrice(label=title, amount=amount)]
    await bot.send_invoice(
        chat_id=user_id,
        title=title,
        description=f"Доступ к анализу фото еды на {days} дней",
        prices=prices,
        provider_token=settings.PROVIDER_TOKEN,
        payload=f"sub_{sub_type}_{user_id}",
        currency="RUB",
    )


@router.pre_checkout_query()
async def pre_checkout(query: types.PreCheckoutQuery) -> None:
    await query.answer(ok=True)


@router.message(F.successful_payment)
async def successful_payment(message: types.Message) -> None:
    payment_info = message.successful_payment
    payload = payment_info.invoice_payload

    if not payload.startswith("sub_"):
        await message.answer("Ошибка обработки платежа. Обратитесь в поддержку.")
        return

    parts = payload.split("_")
    sub_type = parts[1]
    user_id = message.from_user.id

    duration_days = 30 if sub_type == "1m" else 90

    async with async_session() as session:
        payment = Payment(
            user_id=user_id,
            amount=payment_info.total_amount,
            currency=payment_info.currency,
            sub_type=sub_type,
            telegram_payment_id=payment_info.telegram_payment_charge_id,
            status="success",
        )
        session.add(payment)
        await activate_subscription(session, user_id, sub_type, duration_days)

    await message.answer(
        "✅ Оплата прошла успешно! Подписка активирована.\n\n"
        "📸 Теперь вы можете отправлять фото еды для анализа.",
        reply_markup=main_menu_keyboard(),
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
