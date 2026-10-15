import logging

from aiogram import Bot
from aiogram.types import InputMediaPhoto

from app.config import config
from app.database.db import async_session
from app.database.repository import (
    set_order_card_info,
    set_order_photos_message_id,
)
from app.keyboards import order_admin_kb
from app.keyboards.admin_kb import ORDER_STATUSES

logger = logging.getLogger(__name__)

CURRENCY_SUFFIX = "Br"


def format_price(price: str) -> str:
    price = price.strip()
    if not price:
        return ""
    lower = price.lower()
    if "br" in lower or "руб" in lower or "бр" in lower or "byn" in lower:
        return price
    return f"{price} {CURRENCY_SUFFIX}"


def _price_line(price: str) -> str:
    if not price:
        return "💰 Цена: <i>не указана</i>"
    return f"💰 Цена: <b>{format_price(price)}</b>"


def _build_order_caption(
    order_id: int,
    client_id: int,
    username: str | None,
    name: str,
    phone: str,
    description: str,
    price: str = "",
) -> str:
    username_line = f"🔗 Username: @{username}" if username else "🔗 Username: —"

    return (
        f"📦 <b>НОВЫЙ ЗАКАЗ №{order_id}</b>\n"
        "━━━━━━━━━━━━━━━━━━\n"
        f"👤 Имя: {name}\n"
        f"📞 Телефон: {phone}\n"
        f"📦 Заказ: {description}\n"
        "━━━━━━━━━━━━━━━━━━\n"
        f"🆔 Клиент: <code>{client_id}</code>\n"
        f"{username_line}\n"
        "━━━━━━━━━━━━━━━━━━\n"
        f"{_price_line(price)}\n"
        "━━━━━━━━━━━━━━━━━━\n"
        f"Статус: {ORDER_STATUSES['new']}"
    )


async def send_order_to_admins(
    bot: Bot,
    order_id: int,
    client_id: int,
    username: str | None,
    full_name: str,
    name: str,
    phone: str,
    description: str,
    photos: list[str] | None = None,
    price: str = "",
) -> bool:
    caption = _build_order_caption(
        order_id=order_id,
        client_id=client_id,
        username=username,
        name=name,
        phone=phone,
        description=description,
        price=price,
    )
    keyboard = order_admin_kb(order_id, client_id, current_status="new")

    try:
        if photos:
            media = [
                InputMediaPhoto(
                    media=file_id,
                    caption=f"📷 Фото к заказу №{order_id}" if i == 0 else None,
                )
                for i, file_id in enumerate(photos)
            ]
            photos_group = await bot.send_media_group(
                chat_id=config.ADMIN_GROUP_ID,
                message_thread_id=config.ORDERS_THREAD_ID,
                media=media,
            )
            photos_msg_id = photos_group[0].message_id

            card_message = await bot.send_message(
                chat_id=config.ADMIN_GROUP_ID,
                message_thread_id=config.ORDERS_THREAD_ID,
                text=caption,
                reply_markup=keyboard,
            )

            async with async_session() as session:
                await set_order_card_info(
                    session, order_id, card_message.message_id, caption
                )
                await set_order_photos_message_id(
                    session, order_id, photos_msg_id
                )
        else:
            card_message = await bot.send_message(
                chat_id=config.ADMIN_GROUP_ID,
                message_thread_id=config.ORDERS_THREAD_ID,
                text=caption,
                reply_markup=keyboard,
            )
            async with async_session() as session:
                await set_order_card_info(
                    session, order_id, card_message.message_id, caption
                )

        return True
    except Exception as e:
        logger.exception("Ошибка отправки заказа в группу: %s", e)
        return False


def replace_status_line(text: str, new_status_text: str) -> str:
    lines = text.split("\n")
    for i in range(len(lines) - 1, -1, -1):
        if lines[i].startswith("Статус:"):
            lines[i] = f"Статус: {new_status_text}"
            return "\n".join(lines)
    return text + f"\nСтатус: {new_status_text}"


def replace_price_line(text: str, new_price_text: str) -> str:
    formatted = format_price(new_price_text)
    lines = text.split("\n")
    for i, line in enumerate(lines):
        if line.startswith("💰 Цена:"):
            lines[i] = f"💰 Цена: <b>{formatted}</b>"
            return "\n".join(lines)
    for i, line in enumerate(lines):
        if line.startswith("Статус:"):
            lines.insert(i, f"💰 Цена: <b>{formatted}</b>")
            return "\n".join(lines)
    return text + f"\n💰 Цена: <b>{formatted}</b>"