from aiogram.fsm.state import State, StatesGroup


class OrderForm(StatesGroup):
    waiting_for_name = State()
    waiting_for_phone = State()
    waiting_for_description = State()
    waiting_for_photo = State()
    waiting_for_confirm = State()