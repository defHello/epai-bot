from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton


ORDER_STATUSES = {
    "new":       "🆕 Новый",
    "process":   "🔧 В обработке",
    "ordered":   "📦 Заказан",
    "stock":     "🚚 На складе",
    "done":      "✅ Выполнено",
    "cancelled": "❌ Отменён",
}

STATUS_FLOW = {
    "new":     ("process", "🔧 Взять в обработку"),
    "process": ("ordered", "📦 Заказать"),
    "ordered": ("stock",   "🚚 Отправить на склад"),
    "stock":   ("done",    "✅ Выдать клиенту"),
}


def order_admin_kb(
    order_id: int,
    client_id: int,
    current_status: str = "new",
) -> InlineKeyboardMarkup | None:
    """
    Кнопки управления заказом:
    - «Указать цену» (всегда, пока заказ не закрыт)
    - «Следующий статус» (если есть куда идти)
    Возвращает None, если заказ закрыт (done/cancelled).
    """
    if current_status in ("done", "cancelled"):
        return None

    buttons = []

    # Кнопка цены — доступна на всех этапах
    buttons.append([
        InlineKeyboardButton(
            text="💰 Указать цену",
            callback_data=f"setprice:{order_id}:{client_id}",
        )
    ])

    transition = STATUS_FLOW.get(current_status)
    if transition:
        next_status, button_text = transition
        buttons.append([
            InlineKeyboardButton(
                text=button_text,
                callback_data=f"status:{next_status}:{order_id}:{client_id}",
            )
        ])

    if not buttons:
        return None

    return InlineKeyboardMarkup(inline_keyboard=buttons)