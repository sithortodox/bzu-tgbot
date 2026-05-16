import asyncio
import logging

from aiohttp import web

from aiogram import Bot, Dispatcher
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties

from bot.config import settings
from bot.database import async_session, engine, Base
from bot.handlers import start, photo, subscription, profile, history, menu, admin
from bot.models import Payment
from bot.services.reminder import start_scheduler, shutdown_scheduler
from bot.services.subscription import activate_subscription
from bot.services.yookassa import verify_notification, parse_notification

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

bot_instance: Bot | None = None


async def yookassa_webhook(request: web.Request) -> web.Response:
    body = await request.text()
    signature = request.headers.get("X-Content-SHA256", "")

    if not verify_notification(body, signature):
        logger.warning("YooKassa webhook: invalid signature")
        return web.Response(status=400)

    notification = parse_notification(body)
    if not notification:
        logger.warning("YooKassa webhook: invalid body")
        return web.Response(status=400)

    event = notification["event"]
    payment_id = notification["payment_id"]
    status = notification["status"]
    user_id = notification["user_id"]
    sub_type = notification["sub_type"]

    logger.info("YooKassa webhook: event=%s payment=%s user=%d status=%s", event, payment_id, user_id, status)

    if event == "payment.succeeded" and status == "succeeded":
        duration_days = 30 if sub_type == "1m" else 90
        async with async_session() as session:
            result = await session.execute(
                Payment.__table__.select().where(Payment.telegram_payment_id == payment_id)
            )
            row = result.first()
            if row and row.status != "success":
                await session.execute(
                    Payment.__table__.update()
                    .where(Payment.telegram_payment_id == payment_id)
                    .values(status="success")
                )
                await activate_subscription(session, user_id, sub_type, duration_days)

        if bot_instance and user_id:
            try:
                await bot_instance.send_message(
                    user_id,
                    "✅ Оплата прошла успешно! Подписка активирована.\n\n📸 Теперь вы можете отправлять фото еды для анализа.",
                )
            except Exception as e:
                logger.error("YooKassa webhook: failed to notify user %d: %s", user_id, e)

    return web.Response(status=200)


async def on_startup() -> None:
    global bot_instance
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    start_scheduler()
    logger.info("Bot started")


async def on_shutdown() -> None:
    shutdown_scheduler()
    await engine.dispose()
    logger.info("Bot stopped")


def main() -> None:
    global bot_instance
    bot_instance = Bot(
        token=settings.BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = Dispatcher()

    dp.include_router(start.router)
    dp.include_router(photo.router)
    dp.include_router(subscription.router)
    dp.include_router(profile.router)
    dp.include_router(history.router)
    dp.include_router(menu.router)
    dp.include_router(admin.router)

    dp.startup.register(on_startup)
    dp.shutdown.register(on_shutdown)

    app = web.Application()
    app.router.add_post("/yookassa/webhook", yookassa_webhook)

    runner = web.AppRunner(app)
    loop = asyncio.get_event_loop()
    loop.run_until_complete(runner.setup())
    site = web.TCPSite(runner, settings.WEBAPP_HOST, settings.WEBAPP_PORT)
    loop.run_until_complete(site.start())
    logger.info("Webhook server started on %s:%s", settings.WEBAPP_HOST, settings.WEBAPP_PORT)

    logger.info("Starting BZUbot...")
    dp.run_polling(bot_instance)


if __name__ == "__main__":
    main()
