import logging
import time

import redis.asyncio as redis

from bot.config import settings

logger = logging.getLogger(__name__)

redis_client = redis.from_url(settings.REDIS_URL, decode_responses=True)

RATE_LIMIT_PHOTOS_PER_MINUTE = 5
RATE_LIMIT_ANALYSES_PER_DAY = 50
RATE_LIMIT_WINDOW_MINUTE = 60
RATE_LIMIT_WINDOW_DAY = 86400


async def check_rate_limit(user_id: int) -> tuple[bool, str | None]:
    minute_key = f"rate:{user_id}:minute"
    day_key = f"rate:{user_id}:day"

    now = time.time()

    pipe = redis_client.pipeline()
    pipe.incr(minute_key)
    pipe.expire(minute_key, RATE_LIMIT_WINDOW_MINUTE)
    pipe.incr(day_key)
    pipe.expire(day_key, RATE_LIMIT_WINDOW_DAY)
    results = await pipe.execute()

    minute_count = results[0]
    day_count = results[2]

    if minute_count > RATE_LIMIT_PHOTOS_PER_MINUTE:
        return False, "Слишком много запросов. Подождите немного."
    if day_count > RATE_LIMIT_ANALYSES_PER_DAY:
        return False, "Дневной лимит анализов (50) исчерпан. Попробуйте завтра."
    return True, None


async def check_duplicate_photo(user_id: int, file_id: str) -> bool:
    key = f"photo:{user_id}:{file_id}"
    exists = await redis_client.exists(key)
    if exists:
        return True
    await redis_client.set(key, "1", ex=300)
    return False
