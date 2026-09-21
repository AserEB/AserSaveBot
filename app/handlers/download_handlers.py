import os
import uuid
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, FSInputFile

from app import config
from app.core import constants
from app.database import crud
from app.keyboards import inline
from app.services import downloader, compressor
from app.utils import formatting, validators

download_router = Router()

# In-memory session metadata for active download requests
DOWNLOAD_SESSIONS = {}


@download_router.message(F.text & ~F.text.startswith("/"))
async def handle_url_message(message: Message):
    """Interprets pasted links, checks permissions, extracts video info, and presents quality choices."""
    url = message.text.strip()
    platform = validators.detect_platform(url) if hasattr(validators, 'detect_platform') else validators.get_platform_from_url(url)

    if not platform or platform == "Unknown":
        await message.answer(
            "⚠️ Invalid link or unsupported platform. Please send a valid YouTube, TikTok, Instagram, Facebook, or Pinterest URL."
        )
        return

    # Check 24-hour Limit Permission
    allowed, status = crud.can_user_download(message.from_user.id)
    if not allowed:
        await message.answer(
            text=constants.LIMIT_REACHED_TEXT,
            reply_markup=inline.InlineKeyboardMarkup(inline_keyboard=[
                [inline.InlineKeyboardButton(text="⭐️ Get Premium", callback_data="btn_get_premium")],
                [inline.InlineKeyboardButton(text="🔙 Home", callback_data="nav_home")]
            ]),
            parse_mode="HTML"
        )
        return

    processing_msg = await message.answer("🔄 <i>Processing media link... Please wait...</i>", parse_mode="HTML")

    # Extract Video Metadata
    info = await downloader.extract_media_info(url)
    if not info:
        await processing_msg.edit_text("❌ Failed to fetch video information. Please make sure the media link is public.")
        return

    session_id = str(uuid.uuid4())[:8]
    DOWNLOAD_SESSIONS[session_id] = {
        "url": url,
        "title": info.get("title", "Media Video"),
        "duration": info.get("duration", 0),
        "thumbnail": info.get("thumbnail"),
        "platform": platform.lower()
    }

    user = crud.get_or_create_user(message.from_user.id, message.from_user.full_name or "User")
    is_premium = user.get("is_premium") or message.from_user.id in getattr(config, "ADMIN_IDS", [])

    info_text = (
        f"🎬 <b>Title:</b> {info.get('title', 'N/A')}\n"
        f"⏱️ <b>Duration:</b> {formatting.format_duration(info.get('duration', 0))}\n"
        f"🌐 <b>Platform:</b> {platform.capitalize()}\n\n"
        f"👇 Select desired resolution or audio format:"
    )

    await processing_msg.edit_text(
        text=info_text,
        reply_markup=inline.get_download_options_keyboard(session_id, is_premium=is_premium),
        parse_mode="HTML"
    )


@download_router.callback_query(F.data.startswith("dl:"))
async def process_media_download(callback: CallbackQuery):
    """Handles selected resolution download, applies file compression if needed, and delivers file."""
    parts = callback.data.split(":")
    quality = parts[1]
    session_id = parts[2]

    session = DOWNLOAD_SESSIONS.get(session_id)
    if not session:
        await callback.answer("⚠️ Session expired. Please paste the media link again.", show_alert=True)
        return

    user = crud.get_or_create_user(callback.from_user.id, callback.from_user.full_name or "User")
    is_premium = user.get("is_premium") or callback.from_user.id in getattr(config, "ADMIN_IDS", [])

    # Enforce premium for 1080p or Thumbnails
    if quality in ["1080", "thumb"] and not is_premium:
        await callback.answer("🔒 1080p FHD and Thumbnail downloads are exclusive to Premium users!", show_alert=True)
        return

    # Handle Thumbnail Request
    if quality == "thumb":
        thumb_url = session.get("thumbnail")
        if thumb_url:
            await callback.message.delete()
            await callback.message.answer_photo(
                photo=thumb_url,
                caption=f"🖼 <b>Thumbnail:</b> {session['title']}\n\n<i>Downloaded via @AserSaveBot</i>",
                parse_mode="HTML"
            )
            crud.record_successful_download(callback.from_user.id, action_type=session.get("platform", "media"))
            DOWNLOAD_SESSIONS.pop(session_id, None)
        else:
            await callback.answer("❌ Thumbnail not available for this media.", show_alert=True)
        return

    await callback.message.edit_text("⏳ <i>Downloading media file to server... 📊 [████░░░░░░] 40%</i>", parse_mode="HTML")

    # Determine format spec for yt-dlp
    format_map = {
        "1080": "bestvideo[height<=1080]+bestaudio/best",
        "720": "bestvideo[height<=720]+bestaudio/best",
        "480": "bestvideo[height<=480]+bestaudio/best",
        "mp3": "bestaudio/best"
    }
    format_spec = format_map.get(quality, "best")
    ext = "mp3" if quality == "mp3" else "mp4"
    filename = f"{session_id}_{quality}.{ext}"

    # Download File
    downloaded_path = await downloader.download_media_file(session['url'], format_spec, filename)

    if not downloaded_path or not os.path.exists(downloaded_path):
        await callback.message.edit_text("❌ Download failed. The video format might be restricted.")
        return

    file_size_mb = os.path.getsize(downloaded_path) / (1024 * 1024)

    # File Size Handling (>48MB Telegram limit protection)
    if file_size_mb > 48.0 and quality != "mp3":
        if not is_premium:
            downloader.cleanup_file(downloaded_path)
            await callback.message.edit_text(
                "⚠️ File exceeds Telegram's 50MB free limit!\n\n"
                "⭐️ Upgrade to Premium to enable automatic video compression!"
            )
            DOWNLOAD_SESSIONS.pop(session_id, None)
            return

        await callback.message.edit_text("⚡️ <i>File size exceeds 50MB. Compressing video using FFmpeg... 📊</i>", parse_mode="HTML")
        compressed_path = os.path.join(downloader.DOWNLOAD_DIR, f"comp_{filename}")
        result_path = compressor.compress_video(downloaded_path, compressed_path)
        downloader.cleanup_file(downloaded_path)
        downloaded_path = result_path

    if not downloaded_path or not os.path.exists(downloaded_path):
        await callback.message.edit_text("❌ Failed to process video compression.")
        DOWNLOAD_SESSIONS.pop(session_id, None)
        return

    await callback.message.edit_text("📤 <i>Uploading media to Telegram...</i>", parse_mode="HTML")

    # Send Media Document/Video/Audio to user
    try:
        input_file = FSInputFile(downloaded_path)
        caption = f"✨ <b>{session['title']}</b>\n\n<i>Downloaded via @AserSaveBot</i>"

        if quality == "mp3":
            await callback.message.answer_audio(audio=input_file, caption=caption, parse_mode="HTML")
        else:
            await callback.message.answer_video(video=input_file, caption=caption, parse_mode="HTML")

        # Record download in database with detected platform
        crud.record_successful_download(callback.from_user.id, action_type=session.get("platform", "media"))
        await callback.message.delete()

    except Exception as e:
        await callback.message.answer(f"❌ Upload error: {str(e)}")
    finally:
        downloader.cleanup_file(downloaded_path)
        DOWNLOAD_SESSIONS.pop(session_id, None)

    await callback.answer()