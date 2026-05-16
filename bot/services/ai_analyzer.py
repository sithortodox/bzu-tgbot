import base64
import json
import logging

import aiohttp
from PIL import Image
from io import BytesIO

from bot.config import settings

logger = logging.getLogger(__name__)

API_URL = "https://g4f.space/api/pollinations/chat/completions"
MODEL = "openai"

IDENTIFY_PROMPT = """Определи, что за блюдо на фото. Верни ТОЛЬКО JSON без markdown:
{
  "dish_name": "точное название блюда",
  "dish_name_en": "english name for search",
  "composition": "состав ингредиентов",
  "estimated_weight_grams": 250,
  "confidence": "high",
  "error": null
}

Если не еда / не видно / размытое:
{
  "dish_name": null,
  "dish_name_en": null,
  "composition": null,
  "estimated_weight_grams": null,
  "confidence": "low",
  "error": "описание причины"
}"""

NUTRITION_PROMPT = """Рассчитай точную пищевую ценность блюда "{dish_name}" (состав: {composition}, вес порции: {weight}г).
Используй известные табличные данные продуктов. Верни ТОЛЬКО JSON без markdown:
{{
  "dish_name": "{dish_name}",
  "weight_grams": {weight},
  "calories": 0,
  "proteins": 0.0,
  "fats": 0.0,
  "carbs": 0.0,
  "fiber": 0.0,
  "gi": 0,
  "xe": 0.0,
  "bje": 0.0,
  "confidence": "high",
  "data_source": "табличные данные",
  "alternatives": [
    {{
      "name": "название альтернативы",
      "reason": "почему полезнее",
      "calories_per_100g": 0,
      "key_benefit": "ключевая польза"
    }}
  ]
}}

Правила:
- ХЕ = углеводы / 12 (до 1 знака)
- БЖЕ = белки/2 + жиры/2 (до 1 знака)
- ГИ: 0-100
- Укажи 2-3 реалистичных альтернативы с БОЛЬШЕ белка/клетчатки и МЕНЬШЕ жира/сахара
- Альтернативы — блюда, которыми можно заменить данное"""


def _compress_photo(photo_bytes: bytes, max_size: int = 512, quality: int = 50) -> str:
    img = Image.open(BytesIO(photo_bytes)).convert("RGB")
    img.thumbnail((max_size, max_size))
    buf = BytesIO()
    img.save(buf, format="JPEG", quality=quality)
    return base64.b64encode(buf.getvalue()).decode()


async def _g4f_request(messages: list, timeout: int = 90) -> str | None:
    payload = {"model": MODEL, "messages": messages, "stream": False}
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                API_URL, json=payload, timeout=aiohttp.ClientTimeout(total=timeout),
            ) as resp:
                if resp.status != 200:
                    error_text = await resp.text()
                    logger.error("g4f API error: %s %s", resp.status, error_text[:200])
                    return None
                data = await resp.json(content_type=None)
                return data["choices"][0]["message"]["content"]
    except Exception as e:
        logger.error("g4f request error: %s", e)
        return None


def _parse_json(text: str) -> dict | None:
    text = text.strip()
    if text.startswith("```"):
        text = text.split("```")[1]
        if text.startswith("json"):
            text = text[4:]
    try:
        return json.loads(text.strip())
    except json.JSONDecodeError:
        return None


async def analyze_food_photo(photo_bytes: bytes) -> dict:
    try:
        img_b64 = _compress_photo(photo_bytes)

        identify_messages = [{
            "role": "user",
            "content": [
                {"type": "text", "text": IDENTIFY_PROMPT},
                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{img_b64}"}},
            ],
        }]

        content = await _g4f_request(identify_messages, timeout=90)
        if not content:
            return {"error": "ИИ не ответил", "confidence": "low", "dish_name": None}

        identified = _parse_json(content)
        if not identified or identified.get("error") or identified.get("dish_name") is None:
            err = (identified or {}).get("error", "Не удалось распознать блюдо")
            return {"error": err, "confidence": "low", "dish_name": None}

        dish_name = identified["dish_name"]
        dish_en = identified.get("dish_name_en", dish_name)
        composition = identified.get("composition", "")
        weight = identified.get("estimated_weight_grams", 250)
        confidence = identified.get("confidence", "medium")

        logger.info("Identified: %s (en: %s), weight=%sg, conf=%s", dish_name, dish_en, weight, confidence)

        from bot.services.food_database import search_food_database, search_food_web

        db_result = await search_food_database(dish_en or dish_name)

        if db_result and db_result.get("per_100g", {}).get("calories"):
            per100 = db_result["per_100g"]
            ratio = weight / 100.0
            result = {
                "dish_name": dish_name,
                "composition": composition,
                "weight_grams": weight,
                "calories": round(per100["calories"] * ratio, 1) if per100.get("calories") else None,
                "proteins": round(per100["proteins"] * ratio, 1) if per100.get("proteins") else None,
                "fats": round(per100["fats"] * ratio, 1) if per100.get("fats") else None,
                "carbs": round(per100["carbs"] * ratio, 1) if per100.get("carbs") else None,
                "fiber": round(per100["fiber"] * ratio, 1) if per100.get("fiber") else None,
                "gi": None,
                "confidence": "high",
                "data_source": f"Open Food Facts ({db_result.get('product_name', '')})",
            }
        else:
            web_result = await search_food_web(dish_name)
            if web_result and web_result.get("per_100g"):
                per100 = web_result["per_100g"]
                serving = web_result.get("typical_serving_grams", weight)
                ratio = weight / 100.0
                result = {
                    "dish_name": dish_name,
                    "composition": composition,
                    "weight_grams": weight,
                    "calories": round(per100.get("calories", 0) * ratio, 1),
                    "proteins": round(per100.get("proteins", 0) * ratio, 1),
                    "fats": round(per100.get("fats", 0) * ratio, 1),
                    "carbs": round(per100.get("carbs", 0) * ratio, 1),
                    "fiber": round(per100.get("fiber", 0) * ratio, 1),
                    "gi": web_result.get("gi"),
                    "confidence": "high",
                    "data_source": web_result.get("source", "табличные данные"),
                }
            else:
                nutrition_messages = [{
                    "role": "user",
                    "content": NUTRITION_PROMPT.format(
                        dish_name=dish_name, composition=composition, weight=weight
                    ),
                }]
                nutrition_content = await _g4f_request(nutrition_messages, timeout=60)
                nutrition = _parse_json(nutrition_content or "")
                if nutrition:
                    result = nutrition
                    result["composition"] = composition
                    result["confidence"] = confidence
                else:
                    result = {
                        "dish_name": dish_name,
                        "composition": composition,
                        "weight_grams": weight,
                        "calories": None,
                        "proteins": None,
                        "fats": None,
                        "carbs": None,
                        "gi": None,
                        "confidence": "low",
                        "error": "Не удалось рассчитать КБЖУ",
                    }

        if "alternatives" not in result:
            web_result = web_result if 'web_result' in dir() else await search_food_web(dish_name)
            if web_result and web_result.get("alternatives"):
                result["alternatives"] = web_result["alternatives"]
            else:
                alt_messages = [{
                    "role": "user",
                    "content": f"""Предложи 2-3 более полезных альтернативы блюду "{dish_name}" (КБЖУ: ккал={result.get('calories')}, Б={result.get('proteins')}, Ж={result.get('fats')}, У={result.get('carbs')}).
Верни ТОЛЬКО JSON массив без markdown:
[
  {{"name": "название", "reason": "почему полезнее", "calories_per_100g": 0, "key_benefit": "ключевая польза"}}
]
Альтернативы должны содержать больше белка/клетчатки и меньше жира/сахара.""",
                }]
                alt_content = await _g4f_request(alt_messages, timeout=45)
                alt_parsed = _parse_json(alt_content or "")
                if isinstance(alt_parsed, list):
                    result["alternatives"] = alt_parsed

        logger.info("Final: dish=%s cal=%s source=%s alternatives=%d",
                     result.get("dish_name"), result.get("calories"),
                     result.get("data_source", "AI"),
                     len(result.get("alternatives", [])))
        return result

    except Exception as e:
        logger.error("Food analysis error: %s", e)
        return {"error": str(e), "confidence": "low", "dish_name": None}
