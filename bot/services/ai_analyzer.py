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

VISION_PROMPT = """Ты — эксперт по пищевой ценности. Проанализируй это фото еды и верни ТОЛЬКО валидный JSON (без markdown, без комментариев, без ```json```).

Формат ответа:
{
  "dish_name": "название блюда",
  "composition": "примерный состав ингредиентов",
  "weight_grams": 250,
  "calories": 350,
  "proteins": 15.0,
  "fats": 12.0,
  "carbs": 40.0,
  "gi": 55,
  "confidence": "high",
  "error": null
}

Если на фото не еда, фото размытое, слишком тёмное, или несколько блюд без разделения:
{
  "dish_name": null,
  "composition": null,
  "weight_grams": null,
  "calories": null,
  "proteins": null,
  "fats": null,
  "carbs": null,
  "gi": null,
  "confidence": "low",
  "error": "описание причины отказа"
}

Правила:
- Вес порции — примерный, в граммах
- Калории — на указанную порцию
- Белки, жиры, углеводы — в граммах на порцию
- Гликемический индекс — число от 0 до 100
- confidence: "high" / "medium" / "low"
- Все значения примерные, оценивай визуально"""


def _compress_photo(photo_bytes: bytes, max_size: int = 512, quality: int = 50) -> str:
    img = Image.open(BytesIO(photo_bytes)).convert("RGB")
    img.thumbnail((max_size, max_size))
    buf = BytesIO()
    img.save(buf, format="JPEG", quality=quality)
    return base64.b64encode(buf.getvalue()).decode()


async def analyze_food_photo(photo_bytes: bytes) -> dict:
    try:
        img_b64 = _compress_photo(photo_bytes)

        payload = {
            "model": MODEL,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": VISION_PROMPT},
                        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{img_b64}"}},
                    ],
                }
            ],
            "stream": False,
        }

        async with aiohttp.ClientSession() as session:
            async with session.post(
                API_URL,
                json=payload,
                timeout=aiohttp.ClientTimeout(total=90),
            ) as resp:
                if resp.status != 200:
                    error_text = await resp.text()
                    logger.error("g4f API error: %s %s", resp.status, error_text[:200])
                    return {"error": f"API error {resp.status}", "confidence": "low", "dish_name": None}

                text = await resp.text()
                result = json.loads(text)
                content = result["choices"][0]["message"]["content"]

        text_resp = content.strip()
        if text_resp.startswith("```"):
            text_resp = text_resp.split("```")[1]
            if text_resp.startswith("json"):
                text_resp = text_resp[4:]

        parsed = json.loads(text_resp.strip())
        logger.info("AI response: dish=%s confidence=%s", parsed.get("dish_name"), parsed.get("confidence"))
        return parsed
    except json.JSONDecodeError as e:
        logger.error("AI JSON parse error: %s content=%s", e, content[:200] if 'content' in dir() else '?')
        return {"error": "AI вернул невалидный JSON", "confidence": "low", "dish_name": None}
    except Exception as e:
        logger.error("AI analysis error: %s", e)
        return {"error": str(e), "confidence": "low", "dish_name": None}
