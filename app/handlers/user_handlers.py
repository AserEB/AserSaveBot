from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import CommandStart, Command
from aiogram.fsm.context import FSMContext

from app.config import config
from app.core import constants
from app.database import crud
from app.keyboards import inline
from app.utils import formatting

user_router = Router()


@user_router.message(CommandStart())
async def command_start_handler(message: Message, state: FSMContext):
    """Handles /start command, registers user in database, and shows main menu."""
    await state.clear()
    user = crud.get_or_create_user(
        telegram_id=message.from_user.id,
        full_name=message.from_user.full_name or "User",
        username=message.from_user.username
    )
    is_admin = user.get("role") == "admin" or message.from_user.id in config.ADMIN_IDS

    await message.answer(
        text=constants.WELCOME_MESSAGE,
        reply_markup=inline.get_main_menu_keyboard(is_admin=is_admin),
        parse_mode="HTML"
    )


# ---------------- COMMANDS SECTION ----------------

@user_router.message(Command("youtube"))
async def cmd_youtube(message: Message):
    await message.answer(
        "🎬 <b>YouTube Downloader</b>\n\n"
        "Paste any YouTube video or Shorts link directly into this chat to download it in HD video or MP3 audio!",
        parse_mode="HTML"
    )


@user_router.message(Command("tiktok"))
async def cmd_tiktok(message: Message):
    await message.answer(
        "🎵 <b>TikTok Downloader</b>\n\n"
        "Send any TikTok video or sound link directly to download it without watermark!",
        parse_mode="HTML"
    )


@user_router.message(Command("instagram"))
async def cmd_instagram(message: Message):
    await message.answer(
        "📸 <b>Instagram Downloader</b>\n\n"
        "Send any Instagram Reel, Video, or Post URL directly to download high-resolution media!",
        parse_mode="HTML"
    )


@user_router.message(Command("facebook"))
async def cmd_facebook(message: Message):
    user = crud.get_or_create_user(message.from_user.id, message.from_user.full_name or "User")
    is_premium = user.get("is_premium") or message.from_user.id in config.ADMIN_IDS
    status_note = "✅ <i>Your Premium account is ready.</i>" if is_premium else "⚠️ <b>Note:</b> <i>Facebook download is a Premium feature.</i>"
    
    await message.answer(
        f"📘 <b>Facebook Downloader (Premium)</b>\n\n"
        f"Paste any Facebook Reel or Video link directly here.\n\n{status_note}",
        parse_mode="HTML"
    )


@user_router.message(Command("pinterest"))
async def cmd_pinterest(message: Message):
    user = crud.get_or_create_user(message.from_user.id, message.from_user.full_name or "User")
    is_premium = user.get("is_premium") or message.from_user.id in config.ADMIN_IDS
    status_note = "✅ <i>Your Premium account is ready.</i>" if is_premium else "⚠️ <b>Note:</b> <i>Pinterest download is a Premium feature.</i>"
    
    await message.answer(
        f"📌 <b>Pinterest Downloader (Premium)</b>\n\n"
        f"Paste any Pinterest video or Pin link directly here.\n\n{status_note}",
        parse_mode="HTML"
    )


@user_router.message(Command("compress"))
async def cmd_compress(message: Message):
    await message.answer(
        "⚡️ <b>Video Compression Service</b>\n\n"
        "• <b>Automatic Cloud Compression:</b> Any video downloaded above 46MB is compressed via FFmpeg to safely bypass Telegram's file limit.\n"
        "• <b>Direct Video Compression:</b> Send your video file (up to 20MB) directly here, and the bot will compress it to reduce size while preserving quality!\n\n"
        "<i>Note: Compression services are exclusive to Premium subscribers.</i>",
        parse_mode="HTML"
    )


@user_router.message(Command("status"))
async def cmd_status(message: Message):
    """Command alternative to check user status with countdown."""
    user = crud.get_or_create_user(
        telegram_id=message.from_user.id,
        full_name=message.from_user.full_name or "User",
        username=message.from_user.username
    )

    is_premium = user.get("is_premium", False)
    role = "Administrator 👑" if user.get("role") == "admin" else ("Premium User ⭐️" if is_premium else "Free Member 👤")

    status_text = f"<b>👤 Account Profile</b>\n\n"
    status_text += f"• <b>Full Name:</b> {user.get('full_name')}\n"
    status_text += f"• <b>Account Status:</b> {role}\n"

    if is_premium and user.get("premium_expiry"):
        days_left = formatting.calculate_days_remaining(user.get("premium_expiry"))
        status_text += f"• <b>Premium Validity:</b> {days_left} Days Remaining ⏳\n"
    elif user.get("role") != "admin":
        downloads_today = user.get("daily_yt_downloads", 0)
        remaining_downloads = max(0, constants.FREE_DAILY_DOWNLOAD_LIMIT - downloads_today)
        status_text += f"• <b>Free Downloads Today:</b> {remaining_downloads} / {constants.FREE_DAILY_DOWNLOAD_LIMIT}\n"
        
        # 24-hour restore countdown calculation
        if remaining_downloads == 0:
            last_dl = user.get("last_download_at")
            countdown = formatting.calculate_next_download_countdown(last_dl)
            status_text += f"• <b>Next Free Download:</b> {countdown}\n"

    status_text += f"• <b>Total Lifetime Downloads:</b> {user.get('total_downloads', 0)}\n"

    await message.answer(
        text=status_text,
        reply_markup=inline.get_navigation_keyboard(back_to="home"),
        parse_mode="HTML"
    )


# ---------------- CALLBACK QUERIES ----------------

@user_router.callback_query(F.data == "nav_home")
async def nav_home_handler(callback: CallbackQuery, state: FSMContext):
    """Returns user to the main menu keyboard."""
    await state.clear()
    is_admin = callback.from_user.id in config.ADMIN_IDS
    await callback.message.edit_text(
        text=constants.WELCOME_MESSAGE,
        reply_markup=inline.get_main_menu_keyboard(is_admin=is_admin),
        parse_mode="HTML"
    )
    await callback.answer()


@user_router.callback_query(F.data == "btn_about")
async def about_us_handler(callback: CallbackQuery):
    """Shows About Us details with navigation back button."""
    await callback.message.edit_text(
        text=constants.ABOUT_US_TEXT,
        reply_markup=inline.get_navigation_keyboard(back_to="home"),
        parse_mode="HTML"
    )
    await callback.answer()


@user_router.callback_query(F.data == "btn_status")
async def my_status_handler(callback: CallbackQuery):
    """Displays user account status, remaining premium days, and countdown for free restore."""
    user = crud.get_or_create_user(
        telegram_id=callback.from_user.id,
        full_name=callback.from_user.full_name or "User",
        username=callback.from_user.username
    )

    is_premium = user.get("is_premium", False)
    role = "Administrator 👑" if user.get("role") == "admin" else ("Premium User ⭐️" if is_premium else "Free Member 👤")

    status_text = f"<b>👤 Account Profile</b>\n\n"
    status_text += f"• <b>Full Name:</b> {user.get('full_name')}\n"
    status_text += f"• <b>Account Status:</b> {role}\n"

    if is_premium and user.get("premium_expiry"):
        days_left = formatting.calculate_days_remaining(user.get("premium_expiry"))
        status_text += f"• <b>Premium Validity:</b> {days_left} Days Remaining ⏳\n"
    elif user.get("role") != "admin":
        downloads_today = user.get("daily_yt_downloads", 0)
        remaining_downloads = max(0, constants.FREE_DAILY_DOWNLOAD_LIMIT - downloads_today)
        status_text += f"• <b>Free Downloads Today:</b> {remaining_downloads} / {constants.FREE_DAILY_DOWNLOAD_LIMIT}\n"
        
        # 24-hour restore countdown
        if remaining_downloads == 0:
            last_dl = user.get("last_download_at")
            countdown = formatting.calculate_next_download_countdown(last_dl)
            status_text += f"• <b>Next Free Download:</b> {countdown}\n"

    status_text += f"• <b>Total Lifetime Downloads:</b> {user.get('total_downloads', 0)}\n"

    await callback.message.edit_text(
        text=status_text,
        reply_markup=inline.get_navigation_keyboard(back_to="home"),
        parse_mode="HTML"
    )
    await callback.answer()


@user_router.callback_query(F.data == "btn_version")
async def bot_version_handler(callback: CallbackQuery):
    """Displays bot system version, commands guide, and developer attribution."""
    version_text = (
        "🤖 <b>AserSaveBot System Information</b>\n\n"
        "🏷 <b>Version:</b> <code>v1.0 (Stable Release)</code>\n"
        "⚡️ <b>Engine:</b> High-Speed Media Pipeline & FFmpeg Transcoder\n"
        "🎗 <b>Developed by:</b> <b>Aser Production - Visual Creative Solutions 🎗️</b>\n\n"
        "───────────────\n"
        "<b>📋 Available Command Shortcuts:</b>\n"
        "• /start — Restart and display main interactive dashboard\n"
        "• /status — Check your download quotas and subscription validity\n"
        "• /youtube — Instructions for YouTube & Shorts extraction\n"
        "• /tiktok — Instructions for watermark-free TikTok media\n"
        "• /instagram — Instructions for Instagram Reels & Videos\n"
        "• /facebook — Access high-resolution Facebook video downloads (Premium)\n"
        "• /pinterest — Access Pinterest video & pin extraction (Premium)\n"
        "• /compress — Direct video size reduction & auto-compression info\n"
        "• /admin — Administrator Control Dashboard (Authorized users)\n\n"
        "───────────────\n"
        "💡 <i>All rights reserved © 2026 Aser Production. Delivering creative and digital excellence.</i>"
    )
    await callback.message.edit_text(
        text=version_text,
        reply_markup=inline.get_navigation_keyboard(back_to="home"),
        parse_mode="HTML"
    )
    await callback.answer()


@user_router.callback_query(F.data.in_({"btn_yt", "btn_tiktok", "btn_ig", "btn_fb", "btn_pin", "btn_compress"}))
async def platform_button_instruction(callback: CallbackQuery):
    """Guides user on how to download or compress media."""
    platform_names = {
        "btn_yt": "YouTube",
        "btn_tiktok": "TikTok",
        "btn_ig": "Instagram",
        "btn_fb": "Facebook",
        "btn_pin": "Pinterest",
        "btn_compress": "Video Compression"
    }
    p_name = platform_names.get(callback.data, "Media")
    msg = (
        f"📥 <b>How to download from {p_name}:</b>\n\n"
        f"Simply copy the video or audio link from {p_name} and paste/send it directly to this chat!\n\n"
        f"🤞 Or send your video file directly and the bot will compress it!\n\n"
        f"<i>The bot will automatically detect the link and offer download options.</i>"
    )
    await callback.message.edit_text(
        text=msg,
        reply_markup=inline.get_navigation_keyboard(back_to="home"),
        parse_mode="HTML"
    )
    await callback.answer()