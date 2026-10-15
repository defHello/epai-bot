import logging

from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message

from app.config import config
from app.database.db import async_session
from app.database.repository import (
    ACTIVE_STATUSES,
    count_orders_by_status,
    get_active_orders,
)
from app.keyboards.admin_kb import ORDER_STATUSES

logger = logging.getLogger(__name__)
router = Router(name="admin_commands")


@router.message(Command("stats"), F.chat.type == "private")
async def cmd_stats(message: Message) -> None:
    if not config.is_admin(message.from_user.id):
        await message.answer("❌ Команда доступна только администратору.")
        return

    async with async_session() as session:
        counts = await count_orders_by_status(session)
        active_orders = await get_active_orders(session, limit=20)

    total_active = sum(counts.get(s, 0) for s in ACTIVE_STATUSES)
    total_done = counts.get("done", 0)
    total_cancelled = counts.get("cancelled", 0)

    lines = [
        "📊 <b>Статистика заказов</b>",
        "━━━━━━━━━━━━━━━━━━",
    ]

    for status_key, status_text in ORDER_STATUSES.items():
        count = counts.get(status_key, 0)
        lines.append(f"{status_text}: <b>{count}</b>")

    lines.append("━━━━━━━━━━━━━━━━━━")
    lines.append(f"🔵 В работе: <b>{total_active}</b>")
    lines.append(f"✅ Выполнено всего: <b>{total_done}</b>")
    lines.append(f"❌ Отменено: <b>{total_cancelled}</b>")

    if active_orders:
        lines.append("")
        lines.append("📋 <b>Активные заказы:</b>")
        for order in active_orders:
            status_text = ORDER_STATUSES.get(order.status, order.status)
            created = order.created_at.strftime("%d.%m %H:%M") if order.created_at else "—"
            price_line = f" | 💰 {order.price}" if order.price else ""
            lines.append(
                f"• №{order.id} — {status_text} — {created}{price_line}\n"
                f"  👤 {order.name}, 📞 {order.phone}"
            )
    else:
        lines.append("")
        lines.append("📭 Активных заказов нет.")

    text = "\n".join(lines)

    if len(text) > 4000:
        text = text[:4000] + "\n\n... (список обрезан)"

    await message.answer(text)


@router.message(Command("help"), F.chat.type == "private")
async def cmd_help(message: Message) -> None:
    if not config.is_admin(message.from_user.id):
        await message.answer(
            "👋 Этот бот принимает заказы.\n\n"
            "Команды:\n"
            "/start — оформить заказ\n"
            "/my_orders — мои активные заказы"
        )
        return

    await message.answer(
        "🛠 <b>Команды администратора</b>\n\n"
        "/stats — статистика и список активных заказов\n"
        "/help — эта справка\n\n"
        "Управление статусами заказов — кнопками в группе."
    )