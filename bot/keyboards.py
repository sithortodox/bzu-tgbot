from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton, ReplyKeyboardMarkup

from bot.config import settings


def main_menu_keyboard() -> ReplyKeyboardMarkup:
    kb = [
        [KeyboardButton(text="📸 Анализ еды"), KeyboardButton(text="👤 Профиль")],
        [KeyboardButton(text="📋 История"), KeyboardButton(text="💳 Подписка")],
        [KeyboardButton(text="❓ Помощь")],
    ]
    return ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)


def subscription_keyboard() -> InlineKeyboardMarkup:
    kb = [
        [InlineKeyboardButton(text=f"1 месяц — {settings.MONTH_PRICE // 100}₽", callback_data="sub_1m")],
        [InlineKeyboardButton(text=f"3 месяца — {settings.THREE_MONTHS_PRICE // 100}₽", callback_data="sub_3m")],
        [InlineKeyboardButton(text="Проверить подписку", callback_data="sub_check")],
        [InlineKeyboardButton(text="❓ Помощь", callback_data="help")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=kb)


def no_access_keyboard() -> InlineKeyboardMarkup:
    return subscription_keyboard()


def history_keyboard() -> InlineKeyboardMarkup:
    kb = [
        [InlineKeyboardButton(text="📋 Последние 5 приёмов", callback_data="history_5")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="back_menu")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=kb)


def admin_keyboard() -> InlineKeyboardMarkup:
    kb = [
        [InlineKeyboardButton(text="📊 Статистика", callback_data="admin_stats")],
        [InlineKeyboardButton(text="👥 Пользователи", callback_data="admin_users")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="back_menu")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=kb)
