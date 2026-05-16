import logging

from aiogram import Router, types, F
from sqlalchemy import select

from bot.database import async_session
from bot.keyboards import no_access_keyboard
from bot.models import Meal
from bot.services.ai_analyzer import analyze_food_photo
from bot.services.calculator import calculate_xe, calculate_bje, get_bje_warning, get_gi_category
from bot.services.rate_limiter import check_rate_limit, check_duplicate_photo
from bot.services.reminder import schedule_reminder
from bot.services.subscription import check_access

router = Router()
logger = logging.getLogger(__name__)

DISCLAIMER = "\n\n⚠️ Данные приблизительные. Бот не является медицинским сервисом и не заменяет консультацию врача."


@router.message(F.photo)
async def handle_photo(message: types.Message) -> None:
    user_id = message.from_user.id

    async with async_session() as session:
        has_access = await check_access(session, user_id)

    if not has_access:
        await message.answer(
            "У вас нет активной подписки. Оформите для доступа к анализу фото.",
            reply_markup=no_access_keyboard(),
        )
        return

    allowed, reason = await check_rate_limit(user_id)
    if not allowed:
        await message.answer(reason)
        return

    photo = message.photo[-1]
    file_id = photo.file_id

    if await check_duplicate_photo(user_id, file_id):
        await message.answer("Это фото уже обрабатывалось. Отправьте другое.")
        return

    processing_msg = await message.answer("🔍 Определяю блюдо на фото...")

    try:
        file = await message.bot.get_file(file_id)
        photo_bytes = await message.bot.download_file(file.file_path)
        photo_data = photo_bytes.read()
    except Exception as e:
        logger.error("Photo download error: %s", e)
        await processing_msg.edit_text("Не удалось загрузить фото. Попробуйте ещё раз.")
        return

    await processing_msg.edit_text("🔍 Нашёл блюдо, ищу точные данные...")

    ai_result = await analyze_food_photo(photo_data)

    if ai_result.get("error") or ai_result.get("dish_name") is None:
        error_msg = ai_result.get("error", "Не удалось распознать блюдо на фото")
        await processing_msg.edit_text(
            f"❌ {error_msg}\n\nСоветы:\n"
            "• Фото должно быть чётким и светлым\n"
            "• Еда должна быть хорошо видна\n"
            "• На фото должно быть одно блюдо"
        )
        return

    dish_name = ai_result["dish_name"]
    composition = ai_result.get("composition")
    weight = ai_result.get("weight_grams")
    calories = ai_result.get("calories")
    proteins = ai_result.get("proteins")
    fats = ai_result.get("fats")
    carbs = ai_result.get("carbs")
    fiber = ai_result.get("fiber")
    gi = ai_result.get("gi")
    data_source = ai_result.get("data_source")
    alternatives = ai_result.get("alternatives", [])

    xe = ai_result.get("xe") or calculate_xe(carbs)
    bje = ai_result.get("bje") or calculate_bje(proteins, fats)
    bje_warning = get_bje_warning(bje)
    gi_category = get_gi_category(gi)

    async with async_session() as session:
        meal = Meal(
            user_id=user_id,
            photo_file_id=file_id,
            dish_name=dish_name,
            composition=composition,
            weight_grams=weight,
            calories=calories,
            proteins=proteins,
            fats=fats,
            carbs=carbs,
            xe=xe,
            gi=gi,
            bje=bje,
            bje_warning=bje_warning,
        )
        session.add(meal)
        await session.commit()
        await session.refresh(meal)

    if bje is not None:
        try:
            async with async_session() as s:
                await schedule_reminder(message.bot, s, user_id, meal.id)
        except Exception as e:
            logger.error("Reminder scheduling error: %s", e)

    response = f"🍽 <b>{dish_name}</b>\n"
    if composition:
        response += f"📝 Состав: {composition}\n"
    if weight:
        response += f"⚖️ Вес порции: ~{int(weight)} г\n"
    response += "\n"
    if calories is not None:
        response += f"🔥 Калории: {int(calories)} ккал\n"
    if proteins is not None:
        response += f"🥩 Белки: {proteins:.1f} г\n"
    if fats is not None:
        response += f"🧈 Жиры: {fats:.1f} г\n"
    if carbs is not None:
        response += f"🍞 Углеводы: {carbs:.1f} г\n"
    if fiber is not None:
        response += f"🥬 Клетчатка: {fiber:.1f} г\n"
    if xe is not None:
        response += f"🥖 Хлебные единицы: {xe}\n"
    if gi is not None:
        gi_cat = f" ({gi_category})" if gi_category else ""
        response += f"📈 Гликемический индекс: {int(gi)}{gi_cat}\n"
    if bje is not None:
        response += f"💉 БЖЕ: {bje}\n"
    if bje_warning:
        response += f"\n{bje_warning}"
    if data_source:
        response += f"\n📊 Источник данных: {data_source}"

    if alternatives:
        response += "\n\n🔄 <b>Полезные альтернативы:</b>\n"
        for i, alt in enumerate(alternatives[:3], 1):
            name = alt.get("name", "?")
            reason = alt.get("reason", "")
            benefit = alt.get("key_benefit", "")
            cal_100 = alt.get("calories_per_100g")
            line = f"  {i}. <b>{name}</b>"
            if cal_100:
                line += f" — {int(cal_100)} ккал/100г"
            if reason:
                line += f"\n     💡 {reason}"
            if benefit:
                line += f"\n     ✅ {benefit}"
            response += line + "\n"

    response += DISCLAIMER

    await processing_msg.edit_text(response, parse_mode="HTML")
