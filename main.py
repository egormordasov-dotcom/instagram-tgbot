import asyncio
import logging
import os
from dotenv import load_dotenv

from aiogram import Bot, Dispatcher
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram import F
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from database import get_pool, init_db
from handlers import start, accounts, articles, reports, scheduled
from scheduler import sync_all, send_scheduled_reports

load_dotenv()
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)

BOT_TOKEN    = os.environ["BOT_TOKEN"]
ALLOWED_USERS_STR = os.environ.get("ALLOWED_USERS", "")

async def main():
    bot  = Bot(token=BOT_TOKEN)
    pool = await get_pool()
    await init_db(pool)

    # Разрешённые пользователи
    if ALLOWED_USERS_STR:
        allowed = set(int(x.strip()) for x in ALLOWED_USERS_STR.split(",") if x.strip())
        start.ALLOWED_USERS = allowed
        logger.info(f"Разрешённые пользователи: {allowed}")

    dp = Dispatcher()

    # Middleware для передачи pool в хэндлеры
    @dp.update.middleware()
    async def pool_middleware(handler, event, data):
        data["pool"] = pool
        return await handler(event, data)

    # Регистрируем роутеры
    dp.include_router(start.router)
    dp.include_router(accounts.router)
    dp.include_router(articles.router)
    dp.include_router(reports.router)
    dp.include_router(scheduled.router)

    # Навигация — главное меню
    @dp.callback_query(F.data == "menu_main")
    async def menu_main(call: CallbackQuery):
        await call.message.edit_text(
            "Выберите раздел:",
            reply_markup=start.main_menu()
        )

    # Планировщик
    scheduler = AsyncIOScheduler(timezone="Europe/Moscow")
    scheduler.add_job(sync_all,                 "interval", hours=6,   args=[pool])
    scheduler.add_job(send_scheduled_reports,   "cron",     hour="*",  args=[pool, bot])
    scheduler.start()
    logger.info("Планировщик запущен")

    # Запуск бота
    logger.info("Бот запущен")
    await dp.start_polling(bot, allowed_updates=["message", "callback_query"])

if __name__ == "__main__":
    asyncio.run(main())
