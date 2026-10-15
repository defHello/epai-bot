import asyncio
import logging
from logging.handlers import RotatingFileHandler

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.types import BotCommand

from app.config import config
from app.database.db import init_db
from app.handlers import client_router, admin_router, admin_commands_router

log_format = "%(asctime)s - %(levelname)s - %(name)s - %(message)s"

file_handler = RotatingFileHandler(
    "bot.log", maxBytes=5_000_000, backupCount=3, encoding="utf-8"
)
file_handler.setFormatter(logging.Formatter(log_format))

console_handler = logging.StreamHandler()
console_handler.setFormatter(logging.Formatter(log_format))

logging.basicConfig(level=logging.INFO, handlers=[file_handler, console_handler])
logging.getLogger("aiogram.event").setLevel(logging.INFO)

logger = logging.getLogger(__name__)


async def main() -> None:
    await init_db()
    logger.info("База данных готова")

    bot = Bot(
        token=config.BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )

    # Регистрируем команды в меню Telegram
    await bot.set_my_commands([
        BotCommand(command="start", description="Оформить заказ"),
        BotCommand(command="my_orders", description="Мои активные заказы"),
        BotCommand(command="help", description="Помощь"),
    ])

    dp = Dispatcher()

    dp.include_router(admin_commands_router)
    dp.include_router(admin_router)
    dp.include_router(client_router)

    logger.info("Бот запущен")
    await dp.start_polling(bot)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Бот остановлен")