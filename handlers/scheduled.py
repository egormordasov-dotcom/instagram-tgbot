from aiogram import Router, F
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton

router = Router()

def scheduled_menu():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="☀️ Ежедневный",   callback_data="sch_toggle_day")],
        [InlineKeyboardButton(text="📅 Еженедельный", callback_data="sch_toggle_week")],
        [InlineKeyboardButton(text="🗓 Ежемесячный",  callback_data="sch_toggle_month")],
        [InlineKeyboardButton(text="◀️ Назад",        callback_data="menu_main")],
    ])

@router.callback_query(F.data == "menu_scheduled")
async def menu_scheduled(call: CallbackQuery, pool):
    user_id = call.from_user.id
    async with pool.acquire() as conn:
        active = await conn.fetch(
            "SELECT period FROM scheduled_reports WHERE user_id=$1 AND is_active=TRUE",
            user_id
        )
    active_periods = {r["period"] for r in active}

    lines = ["🔔 <b>Авто-отчёты</b>\n", "Выберите тип отчёта для включения/отключения:\n"]
    for period, label in [("day","☀️ Ежедневный"), ("week","📅 Еженедельный"), ("month","🗓 Ежемесячный")]:
        status = "✅" if period in active_periods else "⏸"
        lines.append(f"{status} {label}")

    await call.message.edit_text(
        "\n".join(lines), parse_mode="HTML", reply_markup=scheduled_menu()
    )

@router.callback_query(F.data.startswith("sch_toggle_"))
async def sch_toggle(call: CallbackQuery, pool):
    period = call.data.replace("sch_toggle_", "")
    user_id = call.from_user.id

    async with pool.acquire() as conn:
        existing = await conn.fetchrow(
            "SELECT id, is_active FROM scheduled_reports WHERE user_id=$1 AND period=$2",
            user_id, period
        )
        if existing:
            new_state = not existing["is_active"]
            await conn.execute(
                "UPDATE scheduled_reports SET is_active=$1 WHERE id=$2",
                new_state, existing["id"]
            )
            state_text = "включён ✅" if new_state else "отключён ⏸"
        else:
            await conn.execute(
                "INSERT INTO scheduled_reports (user_id, period, send_hour) VALUES ($1,$2,9)",
                user_id, period
            )
            state_text = "включён ✅"

    period_names = {"day": "Ежедневный", "week": "Еженедельный", "month": "Ежемесячный"}
    await call.answer(f"{period_names.get(period, period)} отчёт {state_text}", show_alert=True)
    await menu_scheduled(call, pool)
