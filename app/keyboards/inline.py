import urllib.parse
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from app.config import config

def get_main_menu_keyboard(is_admin: bool = False) -> InlineKeyboardMarkup:
    """Builds the main interactive keyboard for users."""
    
    # Draft support URL for Contact Us
    draft_text = "Hi Aser Support I need to talk to you about..."
    encoded_draft = urllib.parse.quote(draft_text)
    support_url = f"https://t.me/{config.SUPPORT_USERNAME}?text={encoded_draft}"

    buttons = [
        [
            InlineKeyboardButton(text="🎬 YouTube", callback_data="btn_yt"),
            InlineKeyboardButton(text="🎵 TikTok", callback_data="btn_tiktok")
        ],
        [
            InlineKeyboardButton(text="📸 Instagram", callback_data="btn_ig"),
            InlineKeyboardButton(text="📘 Facebook", callback_data="btn_fb")
        ],
        [
            InlineKeyboardButton(text="📌 Pinterest", callback_data="btn_pin"),
            InlineKeyboardButton(text="⚡ Compress Video", callback_data="btn_compress")
        ],
        [
            InlineKeyboardButton(text="📊 My Status", callback_data="btn_status"),
            InlineKeyboardButton(text="⭐ Get Premium", callback_data="btn_get_premium")
        ],
        [
            InlineKeyboardButton(text="ℹ️ About Us", callback_data="btn_about"),
            InlineKeyboardButton(text="💬 Contact Support", url=support_url)
        ],
        [
            InlineKeyboardButton(text="ℹ️ Bot Version (v1.0)", callback_data="btn_version")
        ]
    ]

    if is_admin:
        buttons.append([InlineKeyboardButton(text="⚙️ Admin Dashboard", callback_data="admin_dashboard")])

    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_download_options_keyboard(video_id: str, is_premium: bool = False) -> InlineKeyboardMarkup:
    """Builds media quality choices for download (1080p, 720p, 480p, MP3 Audio)."""
    buttons = [
        [
            InlineKeyboardButton(
                text="📹 1080p FHD " + ("" if is_premium else "🔒 (Premium)"), 
                callback_data=f"dl:1080:{video_id}"
            ),
            InlineKeyboardButton(
                text="📹 720p HD", 
                callback_data=f"dl:720:{video_id}"
            )
        ],
        [
            InlineKeyboardButton(
                text="📹 480p SD", 
                callback_data=f"dl:480:{video_id}"
            ),
            InlineKeyboardButton(
                text="🎵 MP3 Audio", 
                callback_data=f"dl:mp3:{video_id}"
            )
        ],
        [
            InlineKeyboardButton(
                text="🖼️ Thumbnail " + ("" if is_premium else "🔒 (Premium)"), 
                callback_data=f"dl:thumb:{video_id}"
            )
        ],
        [
            InlineKeyboardButton(text="🔙 Back to Main Menu", callback_data="nav_home")
        ]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_payment_methods_keyboard() -> InlineKeyboardMarkup:
    """Builds bank choices for premium payment."""
    buttons = [
        [
            InlineKeyboardButton(text="🏦 Commercial Bank of Ethiopia (CBE)", callback_data="pay_method:CBE"),
        ],
        [
            InlineKeyboardButton(text="📱 Telebirr", callback_data="pay_method:TELEBIRR")
        ],
        [
            InlineKeyboardButton(text="❌ Cancel", callback_data="nav_cancel")
        ]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_gender_selection_keyboard() -> InlineKeyboardMarkup:
    """Builds gender choices during payment registration flow."""
    buttons = [
        [
            InlineKeyboardButton(text="👨 Male", callback_data="gender:Male"),
            InlineKeyboardButton(text="👩 Female", callback_data="gender:Female")
        ],
        [
            InlineKeyboardButton(text="✏️ Edit Full Name", callback_data="pay_edit_name"),
            InlineKeyboardButton(text="❌ Cancel", callback_data="nav_cancel")
        ]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_admin_approval_keyboard(payment_id: str) -> InlineKeyboardMarkup:
    """Builds Approve/Discard buttons for incoming admin notification."""
    buttons = [
        [
            InlineKeyboardButton(text="✅ Approve Payment", callback_data=f"adm_app:{payment_id}"),
            InlineKeyboardButton(text="❌ Discard Payment", callback_data=f"adm_dis:{payment_id}")
        ]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_navigation_keyboard(back_to: str = "home") -> InlineKeyboardMarkup:
    """Standard back button markup."""
    buttons = [
        [InlineKeyboardButton(text="🔙 Back", callback_data=f"nav_{back_to}")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_admin_dashboard_keyboard() -> InlineKeyboardMarkup:
    """Admin Management Dashboard buttons."""
    buttons = [
        [
            InlineKeyboardButton(text="📊 Detailed Statistics", callback_data="adm_stats"),
            InlineKeyboardButton(text="📤 Send Broadcast", callback_data="adm_broadcast")
        ],
        [
            InlineKeyboardButton(text="📥 Export Premium (CSV)", callback_data="adm_exp_prem"),
            InlineKeyboardButton(text="📥 Export All Users (CSV)", callback_data="adm_exp_all")
        ],
        [
            InlineKeyboardButton(text="📥 Export Discarded (CSV)", callback_data="adm_exp_disc")
        ],
        [
            InlineKeyboardButton(text="🔙 Back to Main Menu", callback_data="nav_home")
        ]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)