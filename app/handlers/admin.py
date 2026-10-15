import asyncio
import logging
import re

from aiogram import Router, F, Bot
from aiogram.types import CallbackQuery, Message

from app.config import config
from app.database.db import async_session
from app.database.repository import (
    update_order_status,
    update_order_price,
    set_order_card_info,
    get_order,
)
from app.keyboards import order_admin_kb, make_order_kb
from app.keyboards.admin_kb import ORDER_STATUSES
from app.services.order_service import (
    replace_status_line,
    replace_price_line,
    format_price,
)

logger = logging.getLogger(__name__)
router = Router(name="admin")


CLIENT_MESSAGES = {
    "process": "🔧 Ваш заказ в обработке.",
    "ordered": "📦 Ваш заказ заказан у поставщика.",
    "stock":   "🚚 Ваш заказ поступил на склад.",
    "done":    "🎉 <b>Ваш заказ готов!</b>\n\nСпасибо, что обратились к нам. Будем рады видеть снова!",
}


# ─────────────── СМЕНА СТАТУСА ───────────────

@router.callback_query(F.data.startswith("status:"))
async def change_status(callback: CallbackQuery, bot: Bot) -> None:
    if not config.is_admin(callback.from_user.id):
        await callback.answer("❌ У вас нет прав.", show_alert=True)
        return

    try:
        _, new_status, order_id_str, client_id_str = callback.data.split(":", 3)
        order_id = int(order_id_str)
        client_id = int(client_id_str)
    except (ValueError, IndexError):
        logger.error("Некорректный callback_data: %s", callback.data)
        await callback.answer("Ошибка данных", show_alert=True)
        return

    if new_status not in ORDER_STATUSES:
        await callback.answer("Неизвестный статус", show_alert=True)
        return

    async with async_session() as session:
        order = await get_order(session, order_id)
        if order is None:
            await callback.answer("Заказ не найден", show_alert=True)
            return
        if order.status == "cancelled":
            await callback.answer("Заказ отменён клиентом", show_alert=True)
            return

    await callback.answer(f"Статус: {ORDER_STATUSES[new_status]}")

    async with async_session() as session:
        await update_order_status(session, order_id, new_status)

    original_text = callback.message.text or callback.message.caption or ""
    new_text = replace_status_line(original_text, ORDER_STATUSES[new_status])
    new_keyboard = order_admin_kb(order_id, client_id, current_status=new_status)

    try:
        await callback.message.edit_text(text=new_text, reply_markup=new_keyboard)
        async with async_session() as session:
            await set_order_card_info(
                session,
                order_id,
                callback.message.message_id,
                new_text,
            )
    except Exception as e:
        logger.exception("Не удалось обновить сообщение заказа: %s", e)

    message_to_client = CLIENT_MESSAGES.get(new_status)
    if message_to_client:
        client_reply_markup = make_order_kb() if new_status == "done" else None

        try:
            await bot.send_message(
                chat_id=client_id,
                text=message_to_client,
                reply_markup=client_reply_markup,
            )
        except Exception as e:
            logger.warning("Не удалось уведомить клиента %s: %s", client_id, e)
            await callback.message.answer(
                f"⚠️ Клиент {client_id} заблокировал бота или недоступен."
            )


# ─────────────── УКАЗАНИЕ ЦЕНЫ (через Reply в топике) ───────────────

@router.callback_query(F.data.startswith("setprice:"))
async def set_price_start(callback: CallbackQuery) -> None:
    if not config.is_admin(callback.from_user.id):
        await callback.answer("❌ У вас нет прав.", show_alert=True)
        return

    try:
        _, order_id_str, client_id_str = callback.data.split(":", 2)
        order_id = int(order_id_str)
    except (ValueError, IndexError):
        await callback.answer("Ошибка данных", show_alert=True)
        return

    async with async_session() as session:
        order = await get_order(session, order_id)
        if order is None:
            await callback.answer("Заказ не найден", show_alert=True)
            return
        if order.status in ("done", "cancelled"):
            await callback.answer("Заказ уже закрыт", show_alert=True)
            return

    await callback.answer("Ответьте на сообщение ниже 👇")

    await callback.message.reply(
        f"💰 <b>Цена для заказа №{order_id}</b>\n\n"
        f"Ответьте <b>на это сообщение</b> ценой.\n"
        f"Например: <code>1500</code>\n"
        f"Валюта (Br) подставится автоматически."
    )


@router.message(F.reply_to_message, F.text, F.chat.id == config.ADMIN_GROUP_ID)
async def set_price_by_reply(message: Message, bot: Bot) -> None:
    if not config.is_admin(message.from_user.id):
        return

    if message.reply_to_message.from_user.id != bot.id:
        return

    reply_text = message.reply_to_message.text or message.reply_to_message.caption or ""

    if "Цена для заказа №" not in reply_text:
        return

    match = re.search(r"Цена для заказа №(\d+)", reply_text)
    if not match:
        return

    order_id = int(match.group(1))

    price = message.text.strip()
    if len(price) > 50:
        await message.reply("Слишком длинная цена. Введите до 50 символов.")
        return

    async with async_session() as session:
        order = await get_order(session, order_id)
        if order is None:
            await message.reply("Заказ не найден.")
            return
        if order.status in ("done", "cancelled"):
            await message.reply("Заказ уже закрыт.")
            return

        await update_order_price(session, order_id, price)
        card_message_id = order.card_message_id
        card_text = order.card_text or ""
        current_status = order.status
        client_id = order.client_id

    formatted = format_price(price)

    # Обновляем карточку заказа в топике
    if card_message_id and card_text:
        new_card_text = replace_price_line(card_text, price)
        try:
            await bot.edit_message_text(
                chat_id=config.ADMIN_GROUP_ID,
                message_id=card_message_id,
                text=new_card_text,
                reply_markup=order_admin_kb(
                    order_id, client_id, current_status=current_status
                ),
            )
            async with async_session() as session:
                await set_order_card_info(
                    session, order_id, card_message_id, new_card_text
                )
        except Exception as e:
            logger.warning("Не удалось обновить карточку заказа: %s", e)

    # 1. Удаляем сообщение-приглашение бота
    try:
        await bot.delete_message(
            chat_id=message.chat.id,
            message_id=message.reply_to_message.message_id,
        )
    except Exception as e:
        logger.warning("Не удалось удалить сообщение-приглашение: %s", e)

    # 2. Удаляем сообщение админа с ценой
    try:
        await bot.delete_message(
            chat_id=message.chat.id,
            message_id=message.message_id,
        )
    except Exception as e:
        logger.warning("Не удалось удалить сообщение админа: %s", e)

    # 3. Отправляем подтверждение и удаляем его через 3 секунды
    confirm_msg = await message.answer(
        f"✅ Цена для заказа №{order_id}: <b>{formatted}</b>"
    )
    await asyncio.sleep(3)
    try:
        await bot.delete_message(
            chat_id=message.chat.id,
            message_id=confirm_msg.message_id,
        )
    except Exception as e:
        logger.warning("Не удалось удалить подтверждение: %s", e)

    # Уведомляем клиента в личку
    try:
        await bot.send_message(
            chat_id=client_id,
            text=(
                f"💰 <b>Стоимость вашего заказа №{order_id}:</b>\n\n"
                f"<b>{formatted}</b>"
            ),
        )
    except Exception as e:
        logger.warning("Не удалось уведомить клиента %s: %s", client_id, e)