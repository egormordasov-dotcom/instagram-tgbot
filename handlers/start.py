from aiogram import Router, F
from aiogram.filters import CommandStart
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton

router = Router()

ALLOWED_USERS = None  # Заполняется из env в main.py

def main_menu():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📱 Аккаунты",    callback_data="menu_accounts")],
        [InlineKeyboardButton(text="🏷 Артикулы",    callback_data="menu_articles")],
        [InlineKeyboardButton(text="📊 Отчёты",      callback_data="menu_reports")],
        [InlineKeyboardButton(text="🔔 Авто-отчёты", callback_data="menu_scheduled")],
    ])

@router.message(CommandStart())
async def cmd_start(message: Message, pool):
    user_id = message.from_user.id

    if ALLOWED_USERS and user_id not in ALLOWED_USERS:
        await message.answer("❌ Доступ запрещён.")
        return

    async with pool.acquire() as conn:
        await conn.execute("""
            INSERT INTO users (id, username) VALUES ($1,$2)
            ON CONFLICT (id) DO UPDATE SET username=EXCLUDED.username
        """, user_id, message.from_user.username)

    await message.answer(
        f"👋 Привет, {message.from_user.first_name}!\n\n"
        "Это бот аналитики Instagram — отслеживает просмотры по артикулам.\n\n"
        "Выберите раздел:",
        reply_markup=main_menu()
    )

@router.callback_query(F.data == "menu_main")
async def menu_main(call: CallbackQuery):
    await call.message.edit_text(
        "Выберите раздел:",
        reply_markup=main_menu()
    )
