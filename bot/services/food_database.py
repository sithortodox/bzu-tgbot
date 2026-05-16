import json
import logging

import aiohttp

logger = logging.getLogger(__name__)

OFF_SEARCH_URL = "https://world.openfoodfacts.org/cgi/search.pl"
OFF_TIMEOUT = 15


async def search_food_database(dish_name: str, lang: str = "ru") -> dict | None:
    try:
        params = {
            "search_terms": dish_name,
            "page_size": 5,
            "json": 1,
        }
        if lang == "ru":
            params["tagtype_0"] = "countries"
            params["tag_contains_0"] = "contains"
            params["tag_0"] = "russia"

        async with aiohttp.ClientSession() as session:
            async with session.get(
                OFF_SEARCH_URL,
                params=params,
                headers={"User-Agent": "BZUbot/1.0"},
                timeout=aiohttp.ClientTimeout(total=OFF_TIMEOUT),
            ) as resp:
                if resp.status != 200:
                    logger.warning("OFF API status %s for '%s'", resp.status, dish_name)
                    return None
                data = await resp.json(content_type=None)

        products = data.get("products", [])
        if not products:
            logger.info("OFF: no results for '%s'", dish_name)
            return None

        best = _pick_best(products, dish_name)
        if not best:
            return None

        nutr = best.get("nutriments", {})
        result = {
            "source": "Open Food Facts",
            "product_name": best.get("product_name", dish_name),
            "brand": best.get("brands", ""),
            "url": best.get("url", ""),
            "per_100g": {
                "calories": nutr.get("energy-kcal_100g"),
                "proteins": nutr.get("proteins_100g"),
                "fats": nutr.get("fat_100g"),
                "carbs": nutr.get("carbohydrates_100g"),
                "fiber": nutr.get("fiber_100g"),
                "sugar": nutr.get("sugars_100g"),
                "sodium": nutr.get("sodium_100g"),
            },
            "serving_size": best.get("serving_quantity") or best.get("serving_size", ""),
        }
        logger.info("OFF: found '%s' — %skcal/100g", result["product_name"], result["per_100g"]["calories"])
        return result
    except Exception as e:
        logger.error("OFF search error for '%s': %s", dish_name, e)
        return None


def _pick_best(products: list, dish_name: str) -> dict | None:
    name_lower = dish_name.lower()
    scored = []
    for p in products:
        pn = (p.get("product_name") or "").lower()
        score = 0
        if name_lower in pn or pn in name_lower:
            score += 10
        nutr = p.get("nutriments", {})
        if nutr.get("energy-kcal_100g") is not None:
            score += 5
        if nutr.get("proteins_100g") is not None:
            score += 3
        if nutr.get("fat_100g") is not None:
            score += 2
        if nutr.get("carbohydrates_100g") is not None:
            score += 2
        scored.append((score, p))
    scored.sort(key=lambda x: x[0], reverse=True)
    return scored[0][1] if scored and scored[0][0] >= 5 else None


async def search_food_web(dish_name: str) -> dict | None:
    search_prompt = f"""Найди точные данные о пищевой ценности блюда "{dish_name}".
Верни ТОЛЬКО JSON без markdown:
{{
  "dish_name": "{dish_name}",
  "per_100g": {{
    "calories": 0,
    "proteins": 0.0,
    "fats": 0.0,
    "carbs": 0.0,
    "fiber": 0.0,
    "sugar": 0.0
  }},
  "typical_serving_grams": 0,
  "gi": 0,
  "source": "источник данных",
  "alternatives": [
    {{
      "name": "название альтернативы",
      "reason": "почему полезнее",
      "calories_per_100g": 0,
      "key_benefit": "ключевая польза"
    }}
  ]
}}

Укажи 2-3 альтернативных блюда, которые содержат больше полезных веществ (клетчатки, белка, витаминов) и меньше жира/сахара. Альтернативы должны быть реалистичными заменами."""

    payload = {
        "model": "openai",
        "messages": [{"role": "user", "content": search_prompt}],
        "stream": False,
    }

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                "https://g4f.space/api/pollinations/chat/completions",
                json=payload,
                timeout=aiohttp.ClientTimeout(total=60),
            ) as resp:
                if resp.status != 200:
                    return None
                data = await resp.json(content_type=None)
                content = data["choices"][0]["message"]["content"]

        text = content.strip()
        if text.startswith("```"):
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]
        result = json.loads(text.strip())
        logger.info("Web search: found data for '%s'", dish_name)
        return result
    except Exception as e:
        logger.error("Web search error for '%s': %s", dish_name, e)
        return None
