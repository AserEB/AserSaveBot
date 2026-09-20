import asyncio
import logging
import sys
import urllib.parse
from aiogram import Bot, Dispatcher
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from app.config import config
from app.handlers import main_router
from app.database import crud

# Setup Application Logging
logging.basicConfig(level=logging.INFO, stream=sys.stdout)


async def premium_expiry_checker_task(bot: Bot):
    """
    Background worker that checks every hour for expired premium subscriptions,
    reverts users to free tier, and sends notification with renewal buttons.
    """
    while True:
        try:
            # Revert expired users in DB and get their Telegram IDs
            expired_user_ids = crud.check_and_get_expired_premium_users()
            
            for user_id in expired_user_ids:
                try:
                    draft_text = "Hi Aser Support I need to talk to you about..."
                    encoded_draft = urllib.parse.quote(draft_text)
                    support_url = f"https://t.me/{config.SUPPORT_USERNAME}?text={encoded_draft}"

                    expiry_text = (
                        "⏰ <b>Your Premium Subscription Has Expired</b>\n\n"
                        "Your account has been reverted to the Normal Free plan (1 download per 24 hours).\n"
                        "Upgrade back to Premium to restore unlimited high-speed downloads and video compression!"
                    )
                    
                    kb = InlineKeyboardMarkup(inline_keyboard=[
                        [InlineKeyboardButton(text="⭐ Get Premium", callback_data="btn_get_premium")],
                        [InlineKeyboardButton(text="💬 Contact Admin", url=support_url)]
                    ])

                    await bot.send_message(
                        chat_id=user_id,
                        text=expiry_text,
                        reply_markup=kb,
                        parse_mode="HTML"
                    )
                except Exception as e:
                    logging.error(f"Failed to send expiry notification to user {user_id}: {e}")

        except Exception as e:
            logging.error(f"Error executing premium expiry checker: {e}")

        # Run check cycle every 1 hour (3600 seconds)
        await asyncio.sleep(3600)


async def main():
    if not config.BOT_TOKEN:
        logging.error("CRITICAL ERROR: BOT_TOKEN is missing in environment setup!")
        return

    # Initialize Bot and Dispatcher
    bot = Bot(token=config.BOT_TOKEN)
    dp = Dispatcher()

    # Register All Application Routers
    dp.include_router(main_router)

    # Launch Background Premium Expiry Task
    asyncio.create_task(premium_expiry_checker_task(bot))

    # Start Bot Long Polling
    logging.info("Aser SaveBot service is starting successfully...")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())