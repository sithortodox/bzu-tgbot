import logging
import sys

from aiogram import Bot, Dispatcher
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties

from bot.config import settings
from bot.database import engine, Base
from bot.handlers import start, photo, subscription, profile, history, menu, admin
from bot.services.reminder import start_scheduler, shutdown_scheduler

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


async def on_startup() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    start_scheduler()
    logger.info("Bot started")


async def on_shutdown() -> None:
    shutdown_scheduler()
    await engine.dispose()
    logger.info("Bot stopped")


def main() -> None:
    bot = Bot(
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

    logger.info("Starting BZUbot...")
    dp.run_polling(bot)


if __name__ == "__main__":
    main()
