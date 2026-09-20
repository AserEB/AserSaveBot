from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext

from app.config import config
from app.core import constants
from app.core.states import PaymentStates
from app.database import crud
from app.keyboards import inline

payment_router = Router()


@payment_router.callback_query(F.data == "btn_get_premium")
async def start_premium_flow(callback: CallbackQuery):
    """Shows premium subscription perks and price."""
    await callback.message.edit_text(
        text=constants.PREMIUM_INFO_TEXT,
        reply_markup=inline.InlineKeyboardMarkup(inline_keyboard=[
            [inline.InlineKeyboardButton(text="💳 Proceed to Payment", callback_data="pay_start")],
            [inline.InlineKeyboardButton(text="🔙 Back", callback_data="nav_home")]
        ]),
        parse_mode="HTML"
    )
    await callback.answer()


@payment_router.callback_query(F.data == "pay_start")
async def ask_full_name(callback: CallbackQuery, state: FSMContext):
    """Initiates registration FSM by asking user's real full name."""
    await state.set_state(PaymentStates.waiting_for_full_name)
    await callback.message.edit_text(
        text="📝 <b>Step 1 of 4: Full Name Registration</b>\n\nPlease send your <b>First Name & Father's Name</b> (e.g., Biruk Girma):",
        reply_markup=inline.get_navigation_keyboard(back_to="cancel"),
        parse_mode="HTML"
    )
    await callback.answer()


@payment_router.callback_query(F.data == "nav_cancel")
async def cancel_payment_process(callback: CallbackQuery, state: FSMContext):
    """Cancels ongoing payment flow."""
    await state.clear()
    await callback.message.edit_text(
        text="❌ Payment registration process cancelled.",
        reply_markup=inline.get_navigation_keyboard(back_to="home"),
        parse_mode="HTML"
    )
    await callback.answer()


@payment_router.message(PaymentStates.waiting_for_full_name, F.text)
async def process_full_name(message: Message, state: FSMContext):
    """Saves full name and prompts for gender selection."""
    full_name = message.text.strip()
    if len(full_name.split()) < 2:
        await message.answer("⚠️ Please enter both your <b>First Name and Father's Name</b>:")
        return

    await state.update_data(registered_name=full_name)
    await state.set_state(PaymentStates.waiting_for_gender)
    await message.answer(
        text=f"👤 <b>Registered Name:</b> {full_name}\n\n<b>Step 2 of 4: Select Gender</b>",
        reply_markup=inline.get_gender_selection_keyboard(),
        parse_mode="HTML"
    )


@payment_router.callback_query(PaymentStates.waiting_for_gender, F.data.startswith("gender:"))
async def process_gender_selection(callback: CallbackQuery, state: FSMContext):
    """Saves gender choice and displays payment method choices."""
    gender = callback.data.split(":")[1]
    await state.update_data(gender=gender)
    await state.set_state(PaymentStates.waiting_for_method)

    await callback.message.edit_text(
        text="💳 <b>Step 3 of 4: Select Payment Method</b>\n\nPlease choose your preferred payment option:",
        reply_markup=inline.get_payment_methods_keyboard(),
        parse_mode="HTML"
    )
    await callback.answer()


@payment_router.callback_query(PaymentStates.waiting_for_gender, F.data == "pay_edit_name")
async def edit_name_handler(callback: CallbackQuery, state: FSMContext):
    """Allows user to re-enter name."""
    await state.set_state(PaymentStates.waiting_for_full_name)
    await callback.message.edit_text(
        text="📝 Please enter your corrected <b>First Name & Father's Name</b>:",
        parse_mode="HTML"
    )
    await callback.answer()


@payment_router.callback_query(PaymentStates.waiting_for_method, F.data.startswith("pay_method:"))
async def process_payment_method(callback: CallbackQuery, state: FSMContext):
    """Displays exact bank account details and requests receipt screenshot upload."""
    method = callback.data.split(":")[1]
    await state.update_data(payment_method=method)
    await state.set_state(PaymentStates.waiting_for_receipt)

    bank = constants.BANK_DETAILS.get(method, {})
    text = (
        f"🏦 <b>Payment Account Details ({bank.get('bank_name')})</b>\n\n"
        f"• <b>Account Name:</b> {bank.get('account_name')}\n"
        f"• <b>Account Number:</b> <code>{bank.get('account_number')}</code>\n"
        f"• <b>Amount Due:</b> {constants.PREMIUM_PRICE_ETB} ETB\n\n"
        f"📌 <b>Step 4 of 4: Receipt Submission</b>\n"
        f"After completing payment, please upload the receipt <b>Screenshot / Photo</b> directly to this chat."
    )

    await callback.message.edit_text(
        text=text,
        reply_markup=inline.get_navigation_keyboard(back_to="cancel"),
        parse_mode="HTML"
    )
    await callback.answer()


@payment_router.message(PaymentStates.waiting_for_receipt, F.photo)
async def process_receipt_photo(message: Message, state: FSMContext):
    """Receives receipt screenshot, saves payment record in Supabase, and alerts admins."""
    data = await state.get_data()
    file_id = message.photo[-1].file_id

    payment = crud.create_payment_request(
        user_id=message.from_user.id,
        registered_name=data.get("registered_name"),
        gender=data.get("gender"),
        payment_method=data.get("payment_method"),
        receipt_file_id=file_id
    )

    await state.clear()

    # Inform User
    await message.answer(
        text="✅ <b>Payment Receipt Received!</b>\n\n"
             "Our team is currently verifying your payment. Your account will be upgraded to Premium within <b>2 - 30 minutes</b>.\n"
             "Thank you for choosing Aser SaveBot!",
        reply_markup=inline.get_navigation_keyboard(back_to="home"),
        parse_mode="HTML"
    )

    # Notify All Admins
    admin_caption = (
        f"🚨 <b>NEW PREMIUM PAYMENT REQUEST</b>\n\n"
        f"• <b>User ID:</b> <code>{message.from_user.id}</code>\n"
        f"• <b>Full Name:</b> {data.get('registered_name')}\n"
        f"• <b>Gender:</b> {data.get('gender')}\n"
        f"• <b>Method:</b> {data.get('payment_method')}\n"
        f"• <b>Payment ID:</b> <code>{payment['id']}</code>"
    )

    for admin_id in config.ADMIN_IDS:
        try:
            await message.bot.send_photo(
                chat_id=admin_id,
                photo=file_id,
                caption=admin_caption,
                reply_markup=inline.get_admin_approval_keyboard(payment["id"]),
                parse_mode="HTML"
            )
        except Exception as e:
            print(f"Error notifying admin {admin_id}: {e}")