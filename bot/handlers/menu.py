import logging

from aiogram import Router, types, F
from aiogram.filters import Command

from bot.keyboards import main_menu_keyboard

router = Router()
logger = logging.getLogger(__name__)


@router.message(F.text == "📸 Анализ еды")
async def btn_analyze(message: types.Message) -> None:
    await message.answer("📸 Отправьте фото блюда для анализа.")


@router.message(F.text == "🔙 Назад")
async def btn_back(callback_or_message: types.Message) -> None:
    await callback_or_message.answer("Главное меню", reply_markup=main_menu_keyboard())


@router.callback_query(F.data == "back_menu")
async def callback_back_menu(callback: types.CallbackQuery) -> None:
    await callback.answer()
    await callback.message.answer("Главное меню", reply_markup=main_menu_keyboard())
