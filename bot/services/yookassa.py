import hashlib
import hmac
import json
import logging
import uuid

import aiohttp

from bot.config import settings

logger = logging.getLogger(__name__)

API_URL = "https://api.yookassa.ru/v3/payments"


def _auth() -> tuple[str, str]:
    return settings.YOOKASSA_SHOP_ID, settings.YOOKASSA_SECRET_KEY


async def create_payment(
    user_id: int,
    sub_type: str,
    amount_rub: float,
    description: str,
) -> dict | None:
    shop_id, secret = _auth()
    if not shop_id or not secret:
        logger.error("YooKassa not configured: shop_id or secret_key missing")
        return None

    idempotence_key = str(uuid.uuid4())
    payload = {
        "amount": {"value": f"{amount_rub:.2f}", "currency": "RUB"},
        "capture": True,
        "confirmation": {
            "type": "redirect",
            "return_url": f"https://t.me/{settings.BOT_TOKEN.split(':')[0]}",
        },
        "description": description,
        "metadata": {
            "user_id": str(user_id),
            "sub_type": sub_type,
        },
    }

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                API_URL,
                json=payload,
                auth=aiohttp.BasicAuth(shop_id, secret),
                headers={
                    "Idempotence-Key": idempotence_key,
                    "Content-Type": "application/json",
                },
                timeout=aiohttp.ClientTimeout(total=20),
            ) as resp:
                if resp.status not in (200, 201):
                    error = await resp.text()
                    logger.error("YooKassa create payment error: %s %s", resp.status, error[:200])
                    return None
                data = await resp.json()
                payment_id = data.get("id")
                confirmation_url = data.get("confirmation", {}).get("confirmation_url")
                logger.info("YooKassa payment created: id=%s user=%d type=%s", payment_id, user_id, sub_type)
                return {
                    "payment_id": payment_id,
                    "confirmation_url": confirmation_url,
                    "status": data.get("status"),
                }
    except Exception as e:
        logger.error("YooKassa create payment exception: %s", e)
        return None


def verify_notification(body: str, request_signature: str) -> bool:
    secret = settings.YOOKASSA_SECRET_KEY
    if not secret or not request_signature:
        return False
    expected = hmac.new(
        secret.encode("utf-8"),
        body.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(expected, request_signature)


def parse_notification(body: str) -> dict | None:
    try:
        data = json.loads(body)
        event = data.get("event")
        payment = data.get("object", {})
        return {
            "event": event,
            "payment_id": payment.get("id"),
            "status": payment.get("status"),
            "paid": payment.get("paid"),
            "amount": payment.get("amount", {}).get("value"),
            "metadata": payment.get("metadata", {}),
            "user_id": int(payment.get("metadata", {}).get("user_id", 0)),
            "sub_type": payment.get("metadata", {}).get("sub_type", ""),
        }
    except Exception as e:
        logger.error("YooKassa notification parse error: %s", e)
        return None


async def get_payment_info(payment_id: str) -> dict | None:
    shop_id, secret = _auth()
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"{API_URL}/{payment_id}",
                auth=aiohttp.BasicAuth(shop_id, secret),
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                if resp.status != 200:
                    return None
                data = await resp.json()
                return {
                    "status": data.get("status"),
                    "paid": data.get("paid"),
                    "metadata": data.get("metadata", {}),
                }
    except Exception as e:
        logger.error("YooKassa get payment error: %s", e)
        return None
