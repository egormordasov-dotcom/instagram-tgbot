from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, Document
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
import io

router = Router()

class ArticleStates(StatesGroup):
    waiting_article = State()

def articles_menu():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Добавить артикул",      callback_data="art_add")],
        [InlineKeyboardButton(text="📎 Загрузить шаблоном",    callback_data="art_template")],
        [InlineKeyboardButton(text="📋 Список артикулов",      callback_data="art_list")],
        [InlineKeyboardButton(text="🗑 Удалить артикул",       callback_data="art_delete")],
        [InlineKeyboardButton(text="◀️ Назад",                callback_data="menu_main")],
    ])

@router.callback_query(F.data == "menu_articles")
async def menu_articles(call: CallbackQuery):
    await call.message.edit_text("🏷 Управление артикулами:", reply_markup=articles_menu())

@router.callback_query(F.data == "art_add")
async def art_add(call: CallbackQuery, state: FSMContext):
    await state.set_state(ArticleStates.waiting_article)
    await call.message.edit_text(
        "Введите артикул (или несколько через запятую):\n"
        "<i>Пример: 279359950, WW385229</i>\n\n"
        "Бот будет искать этот артикул в описаниях Reels.",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="◀️ Отмена", callback_data="menu_articles")]
        ])
    )

@router.message(ArticleStates.waiting_article)
async def art_save(message: Message, state: FSMContext, pool):
    user_id = message.from_user.id
    raw = message.text.strip()
    articles = [a.strip().lstrip("#") for a in raw.replace("\n", ",").split(",") if a.strip()]

    added = []
    skipped = []
    async with pool.acquire() as conn:
        for art in articles:
            try:
                await conn.execute(
                    "INSERT INTO articles (user_id, article) VALUES ($1,$2)",
                    user_id, art
                )
                added.append(art)
            except Exception:
                skipped.append(art)

    await state.clear()
    text = ""
    if added:   text += f"✅ Добавлено: {', '.join(added)}\n"
    if skipped: text += f"⚠️ Уже есть: {', '.join(skipped)}\n"
    await message.answer(text or "Ничего не добавлено.", reply_markup=articles_menu())

@router.callback_query(F.data == "art_template")
async def art_template(call: CallbackQuery):
    await call.answer()
    text = "article\nWW408865\nWW408866\n279359950\n180893337\n"
    file = io.BytesIO(text.encode("utf-8"))
    file.name = "articles_template.csv"
    await call.message.answer_document(
        document=file,
        caption=(
            "📎 <b>Шаблон для загрузки артикулов</b>\n\n"
            "Два варианта:\n"
            "1️⃣ <b>CSV/TXT</b> — один артикул на строку (этот файл)\n"
            "2️⃣ <b>Excel (.xlsx)</b> — артикулы в колонке E\n\n"
            "Заполните и отправьте файл в чат."
        ),
        parse_mode="HTML",
        reply_markup=articles_menu()
    )

@router.message(F.document)
async def art_upload_file(message: Message, pool):
    """Обрабатывает загруженный файл с артикулами — CSV, TXT или Excel."""
    import re
    doc = message.document
    fname = doc.file_name.lower()

    user_id = message.from_user.id
    file    = await message.bot.get_file(doc.file_id)
    content = await message.bot.download_file(file.file_path)
    data    = content.read()

    articles = []

    if fname.endswith((".xlsx", ".xls")):
        # Excel формат — читаем колонку E (индекс 4)
        import io
        import openpyxl
        try:
            wb = openpyxl.load_workbook(io.BytesIO(data), data_only=True)
            ws = wb.active
            for row in ws.iter_rows(min_row=1, values_only=True):
                if len(row) >= 5:
                    val = row[4]  # колонка E
                    if val:
                        art = str(val).strip().lstrip("#").upper()
                        if re.match(r"^WW\w+$", art) or re.match(r"^\d{6,}$", art):
                            articles.append(art)
        except Exception as e:
            await message.answer(f"❌ Ошибка чтения Excel: {e}")
            return

    elif fname.endswith((".csv", ".txt")):
        # CSV/TXT — по одному артикулу на строку
        text = data.decode("utf-8", errors="ignore")
        for line in text.splitlines():
            line = line.strip().lstrip("#")
            if line and line.lower() != "article" and not line.startswith("//"):
                art = line.split(",")[0].strip().lstrip("#").upper()
                if art:
                    articles.append(art)
    else:
        await message.answer(
            "⚠️ Поддерживаются форматы: .xlsx, .csv, .txt\n\n"
            "Отправьте файл в одном из этих форматов."
        )
        return

    if not articles:
        await message.answer(
            "❌ Артикулы не найдены в файле.\n\n"
            "Для Excel: артикулы должны быть в колонке <b>E</b>.\n"
            "Формат: <code>WW408865</code> или числовой артикул.",
            parse_mode="HTML"
        )
        return

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

    await message.answer(
        f"✅ Загружено артикулов: {added}\n"
        f"⚠️ Уже существовало: {skipped}\n\n"
        f"Примеры: {', '.join(articles[:3])}{'...' if len(articles) > 3 else ''}",
        reply_markup=articles_menu()
    )

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
            lines.append(f"• {a['article']} — {a['videos']} видео")
        text = "\n".join(lines)

    await call.message.edit_text(text, parse_mode="HTML", reply_markup=articles_menu())
