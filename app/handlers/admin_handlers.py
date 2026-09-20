import csv
import io
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, BufferedInputFile
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext

from app.config import config
from app.core.states import AdminStates
from app.database import crud
from app.keyboards import inline

admin_router = Router()


@admin_router.message(Command("admin"))
@admin_router.callback_query(F.data == "admin_dashboard")
async def open_admin_dashboard(event: Message | CallbackQuery):
    """Opens administrative dashboard panel."""
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
    """Displays system user metrics and platform extraction counts."""
    if callback.from_user.id not in config.ADMIN_IDS:
        return

    stats = crud.get_system_analytics()
    msg = (
        f"📊 <b>System Performance Analytics</b>\n\n"
        f"👥 <b>Total Users:</b> {stats['total_users']}\n"
        f"⭐ <b>Premium Members:</b> {stats['premium_users']}\n"
        f"👤 <b>Free Members:</b> {stats['normal_users']}\n\n"
        f"📈 <b>Lifetime Extraction Statistics:</b>\n"
        f"• YouTube: {stats['platform_stats'].get('youtube', 0)}\n"
        f"• TikTok: {stats['platform_stats'].get('tiktok', 0)}\n"
        f"• Instagram: {stats['platform_stats'].get('instagram', 0)}\n"
        f"• Compressed Files: {stats['platform_stats'].get('compress', 0)}\n"
    )
    await callback.message.edit_text(msg, reply_markup=inline.get_navigation_keyboard(back_to="admin_dashboard"), parse_mode="HTML")
    await callback.answer()


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

    # Approve and upgrade user to premium
    crud.approve_payment(payment_id, admin_id=callback.from_user.id)

    await callback.message.edit_caption(
        caption=callback.message.caption + f"\n\n✅ <b>APPROVED by {callback.from_user.full_name}</b>",
        parse_mode="HTML"
    )

    # Notify User
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
        # Send user notice
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