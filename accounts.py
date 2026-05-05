from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

router = Router()

class AccountStates(StatesGroup):
    waiting_username = State()

def accounts_menu():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Добавить аккаунт", callback_data="acc_add")],
        [InlineKeyboardButton(text="📋 Мои аккаунты",     callback_data="acc_list")],
        [InlineKeyboardButton(text="🔄 Синхронизировать", callback_data="acc_sync")],
        [InlineKeyboardButton(text="◀️ Назад",            callback_data="menu_main")],
    ])

@router.callback_query(F.data == "menu_accounts")
async def menu_accounts(call: CallbackQuery):
    await call.message.edit_text("📱 Управление аккаунтами Instagram:", reply_markup=accounts_menu())

@router.callback_query(F.data == "acc_add")
async def acc_add(call: CallbackQuery, state: FSMContext):
    await state.set_state(AccountStates.waiting_username)
    await call.message.edit_text(
        "Введите username аккаунта Instagram:\n"
        "<i>Пример: taniii_ugc</i>",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="◀️ Отмена", callback_data="menu_accounts")]
        ])
    )

@router.message(AccountStates.waiting_username)
async def acc_add_username(message: Message, state: FSMContext, pool):
    username = message.text.strip().lstrip("@").lower()
    user_id  = message.from_user.id

    async with pool.acquire() as conn:
        existing = await conn.fetchrow(
            "SELECT id FROM accounts WHERE user_id=$1 AND username=$2 AND platform='instagram'",
            user_id, username
        )
        if existing:
            await message.answer(f"⚠️ Аккаунт @{username} уже добавлен.")
            await state.clear()
            return

        await conn.execute(
            "INSERT INTO accounts (user_id, platform, username) VALUES ($1,'instagram',$2)",
            user_id, username
        )

    await state.clear()
    await message.answer(
        f"✅ Аккаунт @{username} добавлен!\n\n"
        "Данные будут собраны в ближайшие 6 часов.\n"
        "Нажмите «Синхронизировать» чтобы запустить сейчас.",
        reply_markup=accounts_menu()
    )

@router.callback_query(F.data == "acc_list")
async def acc_list(call: CallbackQuery, pool):
    user_id = call.from_user.id
    async with pool.acquire() as conn:
        accounts = await conn.fetch(
            "SELECT username, is_active, "
            "(SELECT COUNT(*) FROM videos WHERE account_id=accounts.id) as video_count "
            "FROM accounts WHERE user_id=$1 AND platform='instagram' ORDER BY created_at",
            user_id
        )

    if not accounts:
        text = "У вас нет добавленных аккаунтов."
    else:
        lines = ["📱 <b>Ваши аккаунты Instagram:</b>\n"]
        for acc in accounts:
            status = "✅" if acc["is_active"] else "⏸"
            lines.append(f"{status} @{acc['username']} — {acc['video_count']} видео")
        text = "\n".join(lines)

    await call.message.edit_text(text, parse_mode="HTML", reply_markup=accounts_menu())

@router.callback_query(F.data == "acc_sync")
async def acc_sync(call: CallbackQuery, pool):
    user_id = call.from_user.id
    await call.message.edit_text("⏳ Запускаем синхронизацию...")

    async with pool.acquire() as conn:
        accounts = await conn.fetch(
            "SELECT id, username FROM accounts WHERE user_id=$1 AND is_active=TRUE AND platform='instagram'",
            user_id
        )

    if not accounts:
        await call.message.edit_text("Нет активных аккаунтов.", reply_markup=accounts_menu())
        return

    from scheduler import sync_account
    import asyncio

    results = []
    for acc in accounts:
        await call.message.edit_text(f"⏳ Синхронизируем @{acc['username']}...")
        try:
            await sync_account(pool, dict(acc))
            results.append(f"✅ @{acc['username']}")
        except Exception as e:
            results.append(f"❌ @{acc['username']}: {e}")
        await asyncio.sleep(1)

    await call.message.edit_text(
        "Синхронизация завершена:\n" + "\n".join(results),
        reply_markup=accounts_menu()
    )
