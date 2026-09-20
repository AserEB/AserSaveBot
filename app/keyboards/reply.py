from aiogram.types import ReplyKeyboardMarkup, KeyboardButton

def get_cancel_reply_keyboard() -> ReplyKeyboardMarkup:
    """Reply Keyboard for cancelling ongoing text input states."""
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="❌ Cancel Operation")]
        ],
        resize_keyboard=True,
        one_time_keyboard=True
    )
    return keyboard