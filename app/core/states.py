from aiogram.fsm.state import State, StatesGroup

class PaymentStates(StatesGroup):
    waiting_for_full_name = State()
    waiting_for_gender = State()
    waiting_for_method = State()
    waiting_for_receipt = State()

class SearchStates(StatesGroup):
    waiting_for_yt_query = State()

class AdminStates(StatesGroup):
    waiting_for_reject_reason = State()
    waiting_for_broadcast_content = State()
    waiting_for_broadcast_confirm = State()