import re
import logging

from aiogram import Router, F, Bot
from aiogram.filters import CommandStart, Command
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    Message,
    CallbackQuery,
    ReplyKeyboardRemove,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)

from app.config import config
from app.keyboards import (
    client_reply_kb,
    make_order_kb,
    client_menu_kb,
    confirm_order_kb,
    cancel_kb,
    photo_step_kb,
    my_order_kb,
)
from app.keyboards.admin_kb import ORDER_STATUSES
from app.states import OrderForm
from app.services.order_service import send_order_to_admins
from app.database.db import async_session
from app.database.repository import (
    MAX_ACTIVE_ORDERS,
    count_active_orders,
    create_order,
    cancel_order,
    get_order,
    get_client_active_orders,
)

logger = logging.getLogger(__name__)
router = Router(name="client")

MAX_PHOTOS = 3

# Телефон: необязательный +, затем цифры, пробелы, дефисы, скобки
PHONE_RE = re.compile(r"^\+?[\d\s\-()]{7,25}$")

# Имя: буквы (кириллица + латиница), пробелы, дефисы, апострофы
NAME_RE = re.compile(r"^[А-Яа-яЁёA-Za-z][А-Яа-яЁёA-Za-z\s\-']{1,49}$")


# ─────────────── СТАРТ ───────────────

@router.message(CommandStart(), F.chat.type == "private")
async def cmd_start(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer(
        "👋 Добро пожаловать!\n\n"
        "Здесь вы можете оформить заказ или посмотреть свои активные заказы.",
        reply_markup=client_reply_kb(),
    )


# ─────────────── REPLY-КНОПКИ ───────────────

@router.message(F.text == "🛒 Сделать заказ", F.chat.type == "private")
async def start_order_by_reply(message: Message, state: FSMContext) -> None:
    await state.clear()

    async with async_session() as session:
        active = await count_active_orders(session, message.from_user.id)

    if active >= MAX_ACTIVE_ORDERS:
        await message.answer(
            f"⚠️ У вас уже {active} активных заказа.\n\n"
            f"Дождитесь, пока они будут выполнены, "
            f"или отмените один через «📋 Мои заказы»."
        )
        return

    await state.set_state(OrderForm.waiting_for_name)
    await message.answer(
        "📝 Шаг 1/4. Введите ваше имя:\n\n"
        "Например: <code>Иван Петров</code>",
        reply_markup=cancel_kb(),
    )


@router.message(F.text == "📋 Мои заказы", F.chat.type == "private")
async def show_my_orders_by_reply(message: Message, state: FSMContext) -> None:
    current = await state.get_state()
    if current is not None:
        await state.clear()

    await _send_my_orders(message, message.from_user.id)


# ─────────────── INLINE-КНОПКИ ───────────────

@router.callback_query(F.data == "start_order")
async def start_order_callback(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()

    async with async_session() as session:
        active = await count_active_orders(session, callback.from_user.id)

    if active >= MAX_ACTIVE_ORDERS:
        await callback.message.answer(
            f"⚠️ У вас уже {active} активных заказа.\n\n"
            f"Дождитесь, пока они будут выполнены, "
            f"или отмените один через «📋 Мои заказы»."
        )
        return

    await state.set_state(OrderForm.waiting_for_name)
    await callback.message.answer(
        "📝 Шаг 1/4. Введите ваше имя:\n\n"
        "Например: <code>Иван Петров</code>",
        reply_markup=cancel_kb(),
    )


@router.callback_query(F.data == "show_my_orders")
async def show_my_orders_callback(callback: CallbackQuery) -> None:
    await callback.answer()
    await _send_my_orders(callback.message, callback.from_user.id)


# ─────────────── ОФОРМЛЕНИЕ ЗАКАЗА ───────────────

@router.message(OrderForm.waiting_for_name, F.text, F.chat.type == "private")
async def process_name(message: Message, state: FSMContext) -> None:
    name = message.text.strip()

    if not NAME_RE.match(name):
        await message.answer(
            "⚠️ Имя может содержать только буквы, пробелы, дефисы "
            "и апострофы.\n\n"
            "Например: <code>Иван Петров</code> или <code>Анна-Мария</code>"
        )
        return

    await state.update_data(name=name)
    await state.set_state(OrderForm.waiting_for_phone)
    await message.answer(
        "📞 Шаг 2/4. Введите ваш номер телефона:\n\n"
        "Например: <code>+375291234567</code>",
        reply_markup=cancel_kb(),
    )


@router.message(OrderForm.waiting_for_phone, F.text, F.chat.type == "private")
async def process_phone(message: Message, state: FSMContext) -> None:
    phone = message.text.strip()

    if not PHONE_RE.match(phone):
        await message.answer(
            "⚠️ Неверный формат номера.\n\n"
            "Введите номер цифрами, можно с <code>+</code>, пробелами, "
            "скобками и дефисами.\n\n"
            "Например: <code>+375291234567</code> "
            "или <code>+375 (29) 123-45-67</code>"
        )
        return

    digits_only = re.sub(r"\D", "", phone)
    if len(digits_only) < 7:
        await message.answer(
            "⚠️ В номере слишком мало цифр. Введите полный номер телефона."
        )
        return

    if len(digits_only) > 15:
        await message.answer(
            "⚠️ В номере слишком много цифр. Проверьте и введите снова."
        )
        return

    await state.update_data(phone=phone)
    await state.set_state(OrderForm.waiting_for_description)
    await message.answer(
        "📦 Шаг 3/4. Опишите ваш заказ:",
        reply_markup=cancel_kb(),
    )


@router.message(OrderForm.waiting_for_description, F.text, F.chat.type == "private")
async def process_description(message: Message, state: FSMContext) -> None:
    if len(message.text) > 1000:
        await message.answer("Слишком длинное описание. Сократите:")
        return
    await state.update_data(description=message.text, photos=[])
    await state.set_state(OrderForm.waiting_for_photo)
    await message.answer(
        f"📷 Шаг 4/4. Пришлите фото (до {MAX_PHOTOS} шт.) "
        "или нажмите «Пропустить / Продолжить».",
        reply_markup=photo_step_kb(),
    )


@router.message(OrderForm.waiting_for_photo, F.photo, F.chat.type == "private")
async def process_photo(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    photos: list[str] = data.get("photos", [])

    if len(photos) >= MAX_PHOTOS:
        await message.answer(
            f"Уже прикреплено {MAX_PHOTOS} фото — максимум. Нажмите «Продолжить»."
        )
        return

    file_id = message.photo[-1].file_id
    photos.append(file_id)
    await state.update_data(photos=photos)

    remaining = MAX_PHOTOS - len(photos)
    if remaining > 0:
        await message.answer(
            f"✅ Фото добавлено ({len(photos)}/{MAX_PHOTOS}). "
            f"Можно прислать ещё {remaining} или нажмите «Продолжить».",
            reply_markup=photo_step_kb(),
        )
    else:
        await message.answer(
            f"✅ Достигнут лимит {MAX_PHOTOS} фото. Нажмите «Продолжить».",
            reply_markup=photo_step_kb(),
        )


@router.callback_query(F.data == "skip_photo")
async def skip_photo(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()

    data = await state.get_data()
    await state.set_state(OrderForm.waiting_for_confirm)

    photos = data.get("photos", [])
    photos_line = f"📷 Фото: {len(photos)} шт." if photos else "📷 Фото: нет"

    preview = (
        "🧾 <b>Проверьте ваш заказ:</b>\n\n"
        f"👤 Имя: {data['name']}\n"
        f"📞 Телефон: {data['phone']}\n"
        f"📦 Заказ: {data['description']}\n"
        f"{photos_line}\n\n"
        "Всё верно?"
    )
    await callback.message.edit_text(preview, reply_markup=confirm_order_kb())


@router.callback_query(F.data == "cancel_order")
async def cancel_order_callback(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    await state.clear()
    await callback.message.edit_text("❌ Заказ отменён.")
    await callback.message.answer(
        "Можете начать заново.",
        reply_markup=client_reply_kb(),
    )


@router.callback_query(F.data == "confirm_order")
async def confirm_order(callback: CallbackQuery, state: FSMContext, bot: Bot) -> None:
    await callback.answer()

    data = await state.get_data()
    await state.clear()

    user = callback.from_user
    photos = data.get("photos", [])

    async with async_session() as session:
        order = await create_order(
            session=session,
            client_id=user.id,
            name=data.get("name", "—"),
            phone=data.get("phone", "—"),
            description=data.get("description", "—"),
            photos=photos,
        )

    success = await send_order_to_admins(
        bot=bot,
        order_id=order.id,
        client_id=user.id,
        username=user.username,
        full_name=user.full_name,
        name=order.name,
        phone=order.phone,
        description=order.description,
        photos=photos,
        price="",
    )

    if success:
        await callback.message.edit_text(
            f"✅ <b>Ваш заказ №{order.id} принят!</b>\n\n"
            "Мы свяжемся с вами в ближайшее время."
        )
    else:
        await callback.message.edit_text(
            "⚠️ Не удалось отправить заказ. Попробуйте позже."
        )


# ─────────────── МОИ ЗАКАЗЫ ───────────────

async def _send_my_orders(target_message: Message, user_id: int) -> None:
    async with async_session() as session:
        orders = await get_client_active_orders(session, user_id)

    if not orders:
        await target_message.answer(
            "📭 У вас нет активных заказов.\n\n"
            "Нажмите «🛒 Сделать заказ» ниже, чтобы оформить первый.",
            reply_markup=client_reply_kb(),
        )
        return

    await target_message.answer("📋 <b>Ваши активные заказы:</b>")

    for order in orders:
        status_text = ORDER_STATUSES.get(order.status, order.status)
        created = order.created_at.strftime("%d.%m %H:%M") if order.created_at else "—"

        price_line = (
            f"💰 Цена: <b>{order.price}</b>"
            if order.price
            else "💰 Цена: <i>не указана</i>"
        )

        card = (
            f"📦 <b>Заказ №{order.id}</b>\n"
            f"📅 {created}\n"
            f"📝 {order.description}\n"
            f"{price_line}\n"
            f"📊 Статус: {status_text}"
        )

        if order.status == "new":
            await target_message.answer(card, reply_markup=my_order_kb(order.id))
        else:
            await target_message.answer(card)


@router.message(Command("my_orders"), F.chat.type == "private")
async def cmd_my_orders(message: Message) -> None:
    await _send_my_orders(message, message.from_user.id)


# ─────────────── ОТМЕНА ЗАКАЗА КЛИЕНТОМ ───────────────

@router.callback_query(F.data.startswith("client_cancel:"))
async def client_cancel_order(callback: CallbackQuery, bot: Bot) -> None:
    await callback.answer()

    try:
        _, order_id_str = callback.data.split(":", 1)
        order_id = int(order_id_str)
    except (ValueError, IndexError):
        await callback.answer("Ошибка данных", show_alert=True)
        return

    user_id = callback.from_user.id

    async with async_session() as session:
        order = await get_order(session, order_id)
        if order is None or order.client_id != user_id:
            await callback.answer("Заказ не найден.", show_alert=True)
            return

        card_message_id = order.card_message_id
        photos_message_id = order.photos_message_id

    async with async_session() as session:
        cancelled = await cancel_order(session, order_id, user_id)

    if cancelled is None:
        await callback.answer(
            "Не удалось отменить заказ. Возможно, он уже взят в работу.",
            show_alert=True,
        )
        return

    if photos_message_id:
        try:
            await bot.delete_message(
                chat_id=config.ADMIN_GROUP_ID,
                message_id=photos_message_id,
            )
        except Exception as e:
            logger.warning("Не удалось удалить фото заказа: %s", e)

    if card_message_id:
        try:
            await bot.delete_message(
                chat_id=config.ADMIN_GROUP_ID,
                message_id=card_message_id,
            )
        except Exception as e:
            logger.warning("Не удалось удалить карточку заказа: %s", e)

    await callback.message.edit_text(
        f"❌ <b>Заказ №{order_id} отменён.</b>\n\n"
        f"Если хотите оформить новый — нажмите «🛒 Сделать заказ».",
        reply_markup=make_order_kb(),
    )


# ─────────────── FALLBACK ───────────────

@router.message(OrderForm.waiting_for_name, ~F.text, F.chat.type == "private")
@router.message(OrderForm.waiting_for_phone, ~F.text, F.chat.type == "private")
@router.message(OrderForm.waiting_for_description, ~F.text, F.chat.type == "private")
async def wrong_input(message: Message) -> None:
    await message.answer("Пожалуйста, отправьте текст.")


@router.message(OrderForm.waiting_for_photo, ~F.photo, F.chat.type == "private")
async def wrong_photo_input(message: Message) -> None:
    await message.answer(
        "Пожалуйста, отправьте фото или нажмите «Пропустить / Продолжить»."
    )


@router.message(F.chat.type == "private")
async def fallback(message: Message, state: FSMContext) -> None:
    current = await state.get_state()
    if current is not None:
        return
    await message.answer(
        "Не понял команду. Используйте кнопки внизу или /start.",
        reply_markup=client_reply_kb(),
    )