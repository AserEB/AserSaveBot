import csv
import io
import asyncio
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, BufferedInputFile, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext

from app.config import config
from app.core.states import AdminStates
from app.database import crud
from app.keyboards import inline

admin_router = Router()


@admin_router.message(Command("admin"))
@admin_router.callback_query(F.data.in_({"admin_dashboard", "nav_admin_dashboard"}))
async def open_admin_dashboard(event: Message | CallbackQuery, state: FSMContext):
    """Opens administrative dashboard panel and clears lingering states."""
    await state.clear()
    user_id = event.from_user.id
    if user_id not in config.ADMIN_IDS:
        return

    text = "👑 <b>Aser SaveBot Administrator Panel</b>\n\nChoose an administrative action from the menu below:"
    reply_markup = inline.get_admin_dashboard_keyboard()

    if isinstance(event, CallbackQuery):
        await event.message.edit_text(text, reply_markup=reply_markup, parse_mode="HTML")
        await event.answer()
    else:
        await event.answer(text, reply_markup=reply_markup, parse_mode="HTML")


@admin_router.callback_query(F.data == "adm_stats")
async def show_admin_stats(callback: CallbackQuery):
    """Displays system user metrics and all platform extraction counts from Supabase."""
    if callback.from_user.id not in config.ADMIN_IDS:
        return

    stats = crud.get_system_analytics()
    plat = stats.get('platform_stats', {})

    msg = (
        f"📊 <b>System Performance Analytics</b>\n\n"
        f"👥 <b>Total Users:</b> {stats.get('total_users', 0)}\n"
        f"⭐ <b>Premium Members:</b> {stats.get('premium_users', 0)}\n"
        f"👤 <b>Free Members:</b> {stats.get('normal_users', 0)}\n\n"
        f"📈 <b>Platform Extraction Counts:</b>\n"
        f"• 🎬 <b>YouTube:</b> {plat.get('youtube', 0)}\n"
        f"• 🎵 <b>TikTok:</b> {plat.get('tiktok', 0)}\n"
        f"• 📸 <b>Instagram:</b> {plat.get('instagram', 0)}\n"
        f"• 📘 <b>Facebook:</b> {plat.get('facebook', 0)}\n"
        f"• 📌 <b>Pinterest:</b> {plat.get('pinterest', 0)}\n"
        f"• ⚡ <b>Compressed Files:</b> {plat.get('compress', 0)}\n"
    )
    await callback.message.edit_text(
        msg, 
        reply_markup=inline.get_navigation_keyboard(back_to="admin_dashboard"), 
        parse_mode="HTML"
    )
    await callback.answer()


# ---------------- BROADCAST SYSTEM ----------------

@admin_router.callback_query(F.data == "adm_broadcast")
async def start_broadcast_flow(callback: CallbackQuery, state: FSMContext):
    """Prompts admin to send any text, photo, or video for broadcasting."""
    if callback.from_user.id not in config.ADMIN_IDS:
        return

    await state.set_state(AdminStates.waiting_for_broadcast_content)
    cancel_kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❌ Cancel Broadcast", callback_data="nav_admin_dashboard")]
    ])
    await callback.message.edit_text(
        "📢 <b>Broadcast Announcement</b>\n\n"
        "Dear Admin, please send the <b>Text message, Photo, or Video</b> (with caption) you want to broadcast to all users:",
        reply_markup=cancel_kb,
        parse_mode="HTML"
    )
    await callback.answer()


@admin_router.message(AdminStates.waiting_for_broadcast_content)
async def preview_broadcast_content(message: Message, state: FSMContext):
    """Saves broadcast message and asks for confirmation."""
    if message.from_user.id not in config.ADMIN_IDS:
        return

    await state.update_data(
        broadcast_chat_id=message.chat.id,
        broadcast_message_id=message.message_id
    )
    await state.set_state(AdminStates.waiting_for_broadcast_confirm)

    confirm_kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Yes, Send to All", callback_data="confirm_broadcast_send"),
            InlineKeyboardButton(text="❌ No, Cancel", callback_data="nav_admin_dashboard")
        ]
    ])

    await message.reply(
        "⚠️ <b>Are you sure you want to broadcast this message to all registered users?</b>",
        reply_markup=confirm_kb,
        parse_mode="HTML"
    )


@admin_router.callback_query(AdminStates.waiting_for_broadcast_confirm, F.data == "confirm_broadcast_send")
async def execute_broadcast(callback: CallbackQuery, state: FSMContext):
    """Iterates through all users and copies the broadcast message."""
    if callback.from_user.id not in config.ADMIN_IDS:
        return

    data = await state.get_data()
    from_chat_id = data.get("broadcast_chat_id")
    message_id = data.get("broadcast_message_id")
    await state.clear()

    await callback.message.edit_text("⏳ <i>Broadcasting in progress... Please wait...</i>", parse_mode="HTML")

    users = crud.get_users_for_export(filter_type="all")
    total = len(users)
    sent_count = 0
    failed_count = 0

    for u in users:
        target_id = u.get("telegram_id")
        if not target_id:
            continue
        try:
            await callback.bot.copy_message(
                chat_id=target_id,
                from_chat_id=from_chat_id,
                message_id=message_id
            )
            sent_count += 1
            await asyncio.sleep(0.05)  # FloodWait መከላከያ
        except Exception:
            failed_count += 1

    report_kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 Back to Dashboard", callback_data="nav_admin_dashboard")]
    ])

    report = (
        f"✅ <b>Broadcast Completed!</b>\n\n"
        f"📊 <b>Total Target Users:</b> {total}\n"
        f"📨 <b>Delivered Successfully:</b> {sent_count}\n"
        f"⚠️ <b>Failed (Blocked/Inactive):</b> {failed_count}"
    )
    await callback.message.edit_text(report, reply_markup=report_kb, parse_mode="HTML")
    await callback.answer()


# ---------------- PAYMENT APPROVAL / DISCARD ----------------

@admin_router.callback_query(F.data.startswith("adm_app:"))
async def approve_payment_handler(callback: CallbackQuery):
    """Handles payment approval with Double Approval Prevention."""
    if callback.from_user.id not in config.ADMIN_IDS:
        return

    payment_id = callback.data.split(":")[1]
    payment = crud.get_payment_by_id(payment_id)

    if not payment or payment.get("status") != "pending":
        handled_by = payment.get("handled_by", "Another Admin") if payment else "Unknown"
        await callback.answer(f"⚠️ Already processed by Admin ID: {handled_by}!", show_alert=True)
        return

    crud.approve_payment(payment_id, admin_id=callback.from_user.id)

    await callback.message.edit_caption(
        caption=callback.message.caption + f"\n\n✅ <b>APPROVED by {callback.from_user.full_name}</b>",
        parse_mode="HTML"
    )

    try:
        await callback.bot.send_message(
            chat_id=payment["user_id"],
            text="🎉 <b>Congratulations! Your Payment Has Been Approved!</b>\n\n"
                 "⭐ Your account has been upgraded to Premium for 30 Days. Enjoy unlimited high-speed downloads!",
            parse_mode="HTML"
        )
    except Exception as e:
        print(f"Error notifying user: {e}")

    await callback.answer("Payment Approved Successfully!", show_alert=True)


@admin_router.callback_query(F.data.startswith("adm_dis:"))
async def start_discard_payment_flow(callback: CallbackQuery, state: FSMContext):
    """Initiates rejection flow and prompts admin for reason."""
    if callback.from_user.id not in config.ADMIN_IDS:
        return

    payment_id = callback.data.split(":")[1]
    payment = crud.get_payment_by_id(payment_id)

    if not payment or payment.get("status") != "pending":
        await callback.answer("⚠️ Payment request already handled!", show_alert=True)
        return

    await state.update_data(reject_payment_id=payment_id)
    await state.set_state(AdminStates.waiting_for_reject_reason)

    await callback.message.reply("📝 Please reply with the <b>reason for rejecting</b> this payment request:")
    await callback.answer()


@admin_router.message(AdminStates.waiting_for_reject_reason, F.text)
async def process_rejection_reason(message: Message, state: FSMContext):
    """Saves rejection reason and alerts user with Contact Support link."""
    data = await state.get_data()
    payment_id = data.get("reject_payment_id")
    reason = message.text.strip()

    payment = crud.discard_payment(payment_id, admin_id=message.from_user.id, reason=reason)
    await state.clear()

    if payment:
        await message.answer(f"❌ Payment request rejected. Reason logged: {reason}")
        try:
            await message.bot.send_message(
                chat_id=payment["user_id"],
                text=f"❌ <b>Payment Request Declined</b>\n\n<b>Reason:</b> {reason}\n\n"
                     f"If you believe this is an error, please click <b>Contact Support</b> below to re-verify.",
                reply_markup=inline.get_main_menu_keyboard(),
                parse_mode="HTML"
            )
        except Exception as e:
            print(f"Error messaging user: {e}")


# ---------------- CSV EXPORTS ----------------

@admin_router.callback_query(F.data.startswith("adm_exp_"))
async def export_users_csv(callback: CallbackQuery):
    """Exports user data as a CSV file."""
    if callback.from_user.id not in config.ADMIN_IDS:
        return

    exp_type = callback.data.replace("adm_exp_", "")
    users = crud.get_users_for_export(filter_type="premium" if exp_type == "prem" else ("discarded" if exp_type == "disc" else "all"))

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Telegram ID", "Full Name", "Username", "Role", "Is Premium", "Total Downloads", "Created At"])

    for u in users:
        writer.writerow([u.get("telegram_id"), u.get("full_name"), u.get("username"), u.get("role"), u.get("is_premium"), u.get("total_downloads"), u.get("created_at")])

    buffer = io.BytesIO(output.getvalue().encode('utf-8'))
    file = BufferedInputFile(buffer.getvalue(), filename=f"users_export_{exp_type}.csv")

    await callback.message.answer_document(document=file, caption=f"📄 Exported {len(users)} user records.")
    await callback.answer()