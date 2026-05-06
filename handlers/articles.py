import io
import re
import openpyxl
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

router = Router()

class ArticleStates(StatesGroup):
    waiting_file = State()

def articles_menu():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Добавить артикулы", callback_data="art_add")],
        [InlineKeyboardButton(text="📋 Список артикулов",  callback_data="art_list")],
        [InlineKeyboardButton(text="🗑 Удалить все",       callback_data="art_delete_all")],
        [InlineKeyboardButton(text="◀️ Назад",            callback_data="menu_main")],
    ])

@router.callback_query(F.data == "menu_articles")
async def menu_articles(call: CallbackQuery):
    await call.message.edit_text("🏷 Управление артикулами:", reply_markup=articles_menu())

# ── Шаг 1: выбираем аккаунт ──────────────────────────────────
@router.callback_query(F.data == "art_add")
async def art_add(call: CallbackQuery, pool):
    user_id = call.from_user.id

    async with pool.acquire() as conn:
        accounts = await conn.fetch(
            "SELECT id, username FROM accounts WHERE user_id=$1 AND is_active=TRUE AND platform='instagram' ORDER BY username",
            user_id
        )

    if not accounts:
        await call.message.edit_text(
            "❌ Сначала добавьте хотя бы один аккаунт Instagram.\n\n"
            "Перейдите в раздел 📱 Аккаунты.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="📱 Аккаунты", callback_data="menu_accounts")],
                [InlineKeyboardButton(text="◀️ Назад",   callback_data="menu_articles")],
            ])
        )
        return

    buttons = []
    for acc in accounts:
        buttons.append([InlineKeyboardButton(
            text=f"@{acc['username']}",
            callback_data=f"art_acc_{acc['id']}"
        )])
    buttons.append([InlineKeyboardButton(text="◀️ Назад", callback_data="menu_articles")])

    await call.message.edit_text(
        "Выберите аккаунт для которого добавляете артикулы:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons)
    )

# ── Шаг 2: просим загрузить файл ─────────────────────────────
@router.callback_query(F.data.startswith("art_acc_"))
async def art_acc_selected(call: CallbackQuery, state: FSMContext, pool):
    account_id = int(call.data.replace("art_acc_", ""))

    async with pool.acquire() as conn:
        acc = await conn.fetchrow("SELECT username FROM accounts WHERE id=$1", account_id)

    if not acc:
        await call.message.edit_text("❌ Аккаунт не найден.")
        return

    await state.set_state(ArticleStates.waiting_file)
    await state.update_data(account_id=account_id, username=acc['username'])

    await call.message.edit_text(
        f"✅ Выбран аккаунт: <b>@{acc['username']}</b>\n\n"
        "Отправьте Excel файл (.xlsx) со списком артикулов.\n\n"
        "📋 <b>Формат файла:</b>\n"
        "• Артикулы в колонке <b>A</b> начиная с ячейки <b>A1</b>\n"
        "• Один артикул на строку\n"
        "• Пример: <code>WW408865</code> или <code>279359950</code>\n"
        "• Решётку # писать не обязательно — бот учтёт оба варианта",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="◀️ Отмена", callback_data="menu_articles")]
        ])
    )

# ── Шаг 3: принимаем файл ────────────────────────────────────
@router.message(ArticleStates.waiting_file, F.document)
async def art_receive_file(message: Message, state: FSMContext, pool):
    doc = message.document

    if not doc.file_name.lower().endswith((".xlsx", ".xls", ".csv", ".txt")):
        await message.answer(
            "⚠️ Пожалуйста отправьте файл в формате .xlsx, .csv или .txt"
        )
        return

    data       = await state.get_data()
    account_id = data['account_id']
    username   = data['username']
    user_id    = message.from_user.id

    # Скачиваем файл
    file    = await message.bot.get_file(doc.file_id)
    content = await message.bot.download_file(file.file_path)
    raw     = content.read()

    # Читаем артикулы
    articles = []
    fname = doc.file_name.lower()

    if fname.endswith((".xlsx", ".xls")):
        try:
            wb = openpyxl.load_workbook(io.BytesIO(raw), data_only=True)
            ws = wb.active
            for row in ws.iter_rows(min_row=1, min_col=1, max_col=1, values_only=True):
                val = row[0]
                if val is not None:
                    art = str(val).strip().lstrip("#").upper()
                    if art:
                        articles.append(art)
        except Exception as e:
            await message.answer(f"❌ Ошибка чтения Excel: {e}")
            await state.clear()
            return
    else:
        text = raw.decode("utf-8", errors="ignore")
        for line in text.splitlines():
            art = line.strip().lstrip("#").upper()
            if art and art.lower() != "article":
                articles.append(art.split(",")[0].strip())

    if not articles:
        await message.answer(
            "❌ Артикулы не найдены.\n\n"
            "Убедитесь что артикулы в колонке A начиная с A1.",
            reply_markup=articles_menu()
        )
        await state.clear()
        return

    # Сохраняем в БД — привязываем к пользователю
    added = skipped = 0
    async with pool.acquire() as conn:
        for art in articles:
            try:
                await conn.execute(
                    "INSERT INTO articles (user_id, article) VALUES ($1,$2)",
                    user_id, art
                )
                added += 1
            except Exception:
                skipped += 1

    await state.clear()

    preview = ", ".join(articles[:5])
    if len(articles) > 5:
        preview += f" ...+{len(articles)-5}"

    await message.answer(
        f"✅ Артикулы для <b>@{username}</b> загружены!\n\n"
        f"• Добавлено: <b>{added}</b>\n"
        f"• Уже было: <b>{skipped}</b>\n\n"
        f"Примеры: <code>{preview}</code>",
        parse_mode="HTML",
        reply_markup=articles_menu()
    )

# ── Если в состоянии ожидания файла прислали текст ───────────
@router.message(ArticleStates.waiting_file)
async def art_waiting_wrong(message: Message):
    await message.answer(
        "⚠️ Пожалуйста отправьте файл .xlsx или .csv\n\n"
        "Или нажмите /start чтобы вернуться в меню."
    )

# ── Список артикулов ─────────────────────────────────────────
@router.callback_query(F.data == "art_list")
async def art_list(call: CallbackQuery, pool):
    user_id = call.from_user.id
    async with pool.acquire() as conn:
        arts = await conn.fetch(
            "SELECT a.article, COUNT(am.video_id) as videos "
            "FROM articles a "
            "LEFT JOIN article_matches am ON am.article_id=a.id "
            "WHERE a.user_id=$1 "
            "GROUP BY a.article ORDER BY a.created_at",
            user_id
        )

    if not arts:
        text = "У вас нет добавленных артикулов."
    else:
        lines = [f"🏷 <b>Ваши артикулы</b> ({len(arts)} шт.):\n"]
        for a in arts:
            lines.append(f"• <code>{a['article']}</code> — {a['videos']} видео")
        text = "\n".join(lines)

    await call.message.edit_text(text, parse_mode="HTML", reply_markup=articles_menu())

# ── Удалить все ───────────────────────────────────────────────
@router.callback_query(F.data == "art_delete_all")
async def art_delete_all(call: CallbackQuery):
    await call.message.edit_text(
        "⚠️ Удалить все артикулы?",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="✅ Да, удалить", callback_data="art_delete_confirm")],
            [InlineKeyboardButton(text="◀️ Отмена",     callback_data="menu_articles")],
        ])
    )

@router.callback_query(F.data == "art_delete_confirm")
async def art_delete_confirm(call: CallbackQuery, pool):
    user_id = call.from_user.id
    async with pool.acquire() as conn:
        result = await conn.execute("DELETE FROM articles WHERE user_id=$1", user_id)
    deleted = result.split()[-1]
    await call.message.edit_text(
        f"✅ Удалено артикулов: {deleted}",
        reply_markup=articles_menu()
    )
