import os
import uuid
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, FSInputFile
from aiogram.exceptions import TelegramBadRequest, TelegramEntityTooLarge

from app import config
from app.core import constants
from app.database import crud
from app.keyboards import inline
from app.services import downloader, compressor
from app.utils import formatting, validators

download_router = Router()

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

    # Check User & Premium Status
    user = crud.get_or_create_user(message.from_user.id, message.from_user.full_name or "User")
    is_premium = user.get("is_premium") or message.from_user.id in getattr(config, "ADMIN_IDS", [])

    # Restrict Facebook & Pinterest to Premium users only
    if platform.lower() in ["facebook", "pinterest"] and not is_premium:
        premium_kb = inline.InlineKeyboardMarkup(inline_keyboard=[
            [inline.InlineKeyboardButton(text="⭐️ Get Premium", callback_data="btn_get_premium")],
            [inline.InlineKeyboardButton(text="🔙 Home", callback_data="nav_home")]
        ])
        await message.answer(
            f"🔒 <b>{platform.capitalize()} Downloads are Premium Only!</b>\n\n"
            f"Due to high server resource usage, {platform.capitalize()} downloads are reserved for Premium subscribers.\n\n"
            f"⭐️ Upgrade now to unlock unlimited access!",
            reply_markup=premium_kb,
            parse_mode="HTML"
        )
        return

    # Check 24-hour Limit Permission for general downloads
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

    info_text = (
        f"🎬 <b>Title:</b> {info.get('title', 'N/A')}\n"
        f"⏱️ <b>Duration:</b> {formatting.format_duration(info.get('duration', 0))}\n"
        f"🌐 <b>Platform:</b> {platform.capitalize()}\n\n"
        f"👇 Select desired resolution or audio format:"
    )

    # platform=platform.lower() እዚህ ጋር ተጨምሯል (ለ YouTube Thumbnail፣ ለሌላው Image ይላል)
    await processing_msg.edit_text(
        text=info_text,
        reply_markup=inline.get_download_options_keyboard(session_id, is_premium=is_premium, platform=platform.lower()),
        parse_mode="HTML"
    )


@download_router.callback_query(F.data.startswith("dl:"))
async def process_media_download(callback: CallbackQuery):
    """Handles selected resolution download, applies file compression if needed, and delivers file."""
    try:
        await callback.answer()
    except Exception:
        pass

    parts = callback.data.split(":")
    quality = parts[1]
    session_id = parts[2]

    session = DOWNLOAD_SESSIONS.get(session_id)
    if not session:
        await callback.message.answer("⚠️ Session expired. Please paste the media link again.")
        return

    user = crud.get_or_create_user(callback.from_user.id, callback.from_user.full_name or "User")
    is_premium = user.get("is_premium") or callback.from_user.id in getattr(config, "ADMIN_IDS", [])

    platform_name = session.get("platform", "media")
    btn_label = "Thumbnail" if platform_name in ["youtube", "yt"] else "Image"

    # Enforce premium for 1080p or Thumbnails/Images
    if quality in ["1080", "thumb"] and not is_premium:
        await callback.message.answer(f"🔒 1080p FHD and {btn_label} downloads are exclusive to Premium users!")
        return

    # Handle Thumbnail / Image Request
    if quality == "thumb":
        await callback.message.edit_text(f"⏳ <i>Fetching {btn_label}...</i>", parse_mode="HTML")
        
        # 1. መጀመሪያ በኮዱ የተያዘው Thumbnail URL ካለ እንሞክራለን
        thumb_url = session.get("thumbnail")
        if thumb_url:
            try:
                await callback.message.delete()
                await callback.message.answer_photo(
                    photo=thumb_url,
                    caption=f"🖼 <b>{btn_label}:</b> {session['title']}\n\n<i>Downloaded via @AserSaveBot</i>",
                    parse_mode="HTML"
                )
                crud.record_successful_download(callback.from_user.id, action_type=platform_name)
                DOWNLOAD_SESSIONS.pop(session_id, None)
                return
            except Exception:
                pass

        # 2. ካልሆነ በ Downloader በኩል ፎቶውን አውርደን እንልካለን
        filename = f"{session_id}_image.jpg"
        downloaded_img = await downloader.download_media_file(session['url'], "thumb", filename)
        if downloaded_img and os.path.exists(downloaded_img):
            input_file = FSInputFile(downloaded_img)
            await callback.message.delete()
            await callback.message.answer_photo(
                photo=input_file,
                caption=f"🖼 <b>{btn_label}:</b> {session['title']}\n\n<i>Downloaded via @AserSaveBot</i>",
                parse_mode="HTML"
            )
            crud.record_successful_download(callback.from_user.id, action_type=platform_name)
            downloader.cleanup_file(downloaded_img)
            DOWNLOAD_SESSIONS.pop(session_id, None)
            return
        else:
            await callback.message.edit_text(f"❌ {btn_label} not available for this media link.")
            DOWNLOAD_SESSIONS.pop(session_id, None)
            return

    await callback.message.edit_text("⏳ <i>Downloading media file to server... 📊 [████░░░░░░] 40%</i>", parse_mode="HTML")

    format_map = {
        "1080": "bv*[height<=1080]+ba/b[height<=1080]/bv*+ba/b/best",
        "720": "bv*[height<=720]+ba/b[height<=720]/bv*+ba/b/best",
        "480": "bv*[height<=480]+ba/b[height<=480]/bv*+ba/b/best",
        "360": "bv*[height<=360]+ba/b[height<=360]/bv*+ba/b/best",
        "240": "bv*[height<=240]+ba/b[height<=240]/bv*+ba/b/best",
        "144": "bv*[height<=144]+ba/b[height<=144]/bv*+ba/b/best",
        "mp3": "ba/ba*/bestaudio/best"
    }
    
    format_spec = format_map.get(quality, "bv*[height<=360]+ba/b/best")
    ext = "mp3" if quality == "mp3" else "mp4"
    filename = f"{session_id}_{quality}.{ext}"

    downloaded_path = await downloader.download_media_file(session['url'], format_spec, filename)

    # 1. ሊንኩ ቪዲዮ ሳይሆን ፎቶ ሆኖ የወረደ ከሆነ
    if downloaded_path and downloaded_path.lower().endswith(('.jpg', '.jpeg', '.png', '.webp')):
        try:
            input_file = FSInputFile(downloaded_path)
            caption = f"🖼 <b>{btn_label}:</b> {session['title']}\n\n<i>Downloaded via @AserSaveBot</i>"
            await callback.message.delete()
            await callback.message.answer_photo(photo=input_file, caption=caption, parse_mode="HTML")
            crud.record_successful_download(callback.from_user.id, action_type=platform_name)
        finally:
            downloader.cleanup_file(downloaded_path)
            DOWNLOAD_SESSIONS.pop(session_id, None)
        return

    # 2. ማውረድ ካልተቻለ (ተጠቃሚው የፎቶ ሊንክ ልኮ የቪዲዮ ጥራት ሲመርጥ)
    if not downloaded_path or not os.path.exists(downloaded_path):
        error_msg = (
            f"⚠️ <b>Your link is not a video, it is an image!</b>\n\n"
            f"Please click the <b>🖼 {btn_label}</b> button to get the photo, or send a valid video link."
        )
        await callback.message.edit_text(error_msg, parse_mode="HTML")
        DOWNLOAD_SESSIONS.pop(session_id, None)
        return

    file_size_mb = os.path.getsize(downloaded_path) / (1024 * 1024)

    # Telegram 50MB Limit Check
    if file_size_mb > 48.0 and quality != "mp3":
        if not is_premium:
            downloader.cleanup_file(downloaded_path)
            await callback.message.edit_text(
                f"⚠️ <b>The video quality MB is high ({file_size_mb:.1f} MB)!</b>\n\n"
                f"Telegram restricts free bots from uploading files larger than <b>50MB</b>.\n\n"
                f"👇 <b>Please choose a lower quality (360p, 240p, 144p, or MP3) below:</b>",
                reply_markup=inline.get_download_options_keyboard(session_id, is_premium=False, platform=platform_name),
                parse_mode="HTML"
            )
            return

        # Compressing for Premium users
        await callback.message.edit_text("⚡️ <i>File exceeds 50MB. Compressing strictly under 40MB with FFmpeg... 📊</i>", parse_mode="HTML")
        compressed_path = await compressor.compress_video_to_size(downloaded_path, target_size_mb=40.0)
        downloader.cleanup_file(downloaded_path)
        downloaded_path = compressed_path

    if not downloaded_path or not os.path.exists(downloaded_path):
        await callback.message.edit_text("❌ Failed to process video compression.")
        DOWNLOAD_SESSIONS.pop(session_id, None)
        return

    await callback.message.edit_text("📤 <i>Uploading media to Telegram...</i>", parse_mode="HTML")

    try:
        input_file = FSInputFile(downloaded_path)
        caption = f"✨ <b>{session['title']}</b>\n\n<i>Downloaded via @AserSaveBot</i>"

        if quality == "mp3":
            await callback.message.answer_audio(audio=input_file, caption=caption, parse_mode="HTML")
        else:
            await callback.message.answer_video(video=input_file, caption=caption, parse_mode="HTML")

        crud.record_successful_download(callback.from_user.id, action_type=platform_name)
        await callback.message.delete()

    except (TelegramBadRequest, TelegramEntityTooLarge) as te:
        if "too large" in str(te).lower() or "entity too large" in str(te).lower():
            await callback.message.answer(
                f"⚠️ <b>The video quality MB is high!</b>\n\n"
                f"Telegram rejected this file. Please choose a lower quality below 👇",
                reply_markup=inline.get_download_options_keyboard(session_id, is_premium=is_premium, platform=platform_name),
                parse_mode="HTML"
            )
        else:
            await callback.message.answer(f"❌ Upload error: {str(te)}")
    except Exception as e:
        await callback.message.answer(f"❌ Upload error: {str(e)}")
    finally:
        downloader.cleanup_file(downloaded_path)
        DOWNLOAD_SESSIONS.pop(session_id, None)


# ---------------- USER DIRECT VIDEO COMPRESSION ----------------

@download_router.message(F.video | (F.document & F.document.mime_type.startswith("video/")))
async def handle_user_video_upload(message: Message):
    """Handles direct video compression requests under Telegram Bot API's 20MB download limit."""
    user = crud.get_or_create_user(message.from_user.id, message.from_user.full_name or "User")
    is_premium = user.get("is_premium") or message.from_user.id in getattr(config, "ADMIN_IDS", [])

    if not is_premium:
        premium_kb = inline.InlineKeyboardMarkup(inline_keyboard=[
            [inline.InlineKeyboardButton(text="⭐️ Get Premium", callback_data="btn_get_premium")],
            [inline.InlineKeyboardButton(text="🔙 Home", callback_data="nav_home")]
        ])
        await message.answer(
            "🔒 <b>Direct Video Compression is a Premium Feature!</b>\n\n"
            "Send your video files and the bot will compress them using high-efficiency FFmpeg to reduce file size.\n\n"
            "⭐️ Upgrade to Premium to use this feature!",
            reply_markup=premium_kb,
            parse_mode="HTML"
        )
        return

    video_obj = message.video or message.document
    file_size = getattr(video_obj, "file_size", 0) or 0
    original_size_mb = file_size / (1024 * 1024)

    if original_size_mb > 20.0:
        await message.answer(
            f"⚠️ <b>File is too large ({original_size_mb:.1f} MB)!</b>\n\n"
            "Telegram's Bot API only allows bots to directly download incoming files up to <b>20MB</b>.\n\n"
            "💡 <b>Tip:</b> For videos larger than 20MB, paste the media link (YouTube, TikTok, Facebook, etc.) directly, and the bot will fetch and compress it automatically from the cloud!",
            parse_mode="HTML"
        )
        return

    status_msg = await message.answer(
        f"📥 <i>Receiving video ({original_size_mb:.1f} MB)... Downloading to server...</i>",
        parse_mode="HTML"
    )

    unique_name = f"upload_{uuid.uuid4().hex[:8]}.mp4"
    local_input_path = os.path.join(downloader.DOWNLOAD_DIR, unique_name)

    try:
        file_info = await message.bot.get_file(video_obj.file_id)
        await message.bot.download_file(file_info.file_path, destination=local_input_path)

        await status_msg.edit_text("⚡️ <i>Compressing video with FFmpeg... 📊</i>", parse_mode="HTML")

        target_mb = max(2.0, original_size_mb * 0.5)
        compressed_path = await compressor.compress_video_to_size(local_input_path, target_size_mb=target_mb)

        if not compressed_path or not os.path.exists(compressed_path):
            await status_msg.edit_text("❌ Video compression failed. The format might not be supported.")
            return

        new_size_mb = os.path.getsize(compressed_path) / (1024 * 1024)
        saved_pct = max(0, int(((original_size_mb - new_size_mb) / original_size_mb) * 100))

        await status_msg.edit_text("📤 <i>Uploading compressed video back to Telegram...</i>", parse_mode="HTML")

        input_file = FSInputFile(compressed_path)
        caption = (
            f"✅ <b>Video Compressed Successfully!</b>\n\n"
            f"📊 <b>Original Size:</b> {original_size_mb:.1f} MB\n"
            f"⚡️ <b>New Size:</b> {new_size_mb:.1f} MB (Saved {saved_pct}%)\n\n"
            f"<i>Processed via @AserSaveBot</i>"
        )

        await message.answer_video(video=input_file, caption=caption, parse_mode="HTML")
        await status_msg.delete()

    except Exception as e:
        await status_msg.edit_text(f"❌ Error processing video: {str(e)}")
    finally:
        downloader.cleanup_file(local_input_path)
        if 'compressed_path' in locals() and compressed_path != local_input_path:
            downloader.cleanup_file(compressed_path)