from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, Any, List
from app.database.db_client import supabase
from app.config import config

# ---------------------------------------------------------
# User Management Functions
# ---------------------------------------------------------

def get_or_create_user(telegram_id: int, full_name: str, username: Optional[str] = None) -> Dict[str, Any]:
    """
    Fetches user from DB. Creates new user if not exists.
    Also handles automatically resetting daily limit if 24 hours passed,
    and downgrading user if premium expired.
    """
    now = datetime.now(timezone.utc)
    role = "admin" if telegram_id in config.ADMIN_IDS else "user"

    # Query user from DB
    response = supabase.table("users").select("*").eq("telegram_id", telegram_id).execute()
    users = response.data

    if not users:
        # Create new user record
        new_user = {
            "telegram_id": telegram_id,
            "full_name": full_name,
            "username": username,
            "role": role,
            "is_premium": False,
            "daily_yt_downloads": 0,
            "total_downloads": 0,
            "created_at": now.isoformat()
        }
        res = supabase.table("users").insert(new_user).execute()
        return res.data[0]

    user = users[0]
    updates = {}

    # Check 1: Premium Expiry Check
    if user.get("is_premium") and user.get("premium_expiry"):
        expiry_dt = datetime.fromisoformat(user["premium_expiry"].replace("Z", "+00:00"))
        if now > expiry_dt:
            updates["is_premium"] = False
            updates["premium_expiry"] = None

    # Check 2: 24-Hour Daily Download Reset Logic
    last_dl = user.get("last_download_date")
    if last_dl:
        last_dl_dt = datetime.fromisoformat(last_dl.replace("Z", "+00:00"))
        if now - last_dl_dt >= timedelta(hours=24):
            updates["daily_yt_downloads"] = 0

    # Apply updates if any status changed
    if updates:
        res = supabase.table("users").update(updates).eq("telegram_id", telegram_id).execute()
        return res.data[0]

    return user


def can_user_download(telegram_id: int) -> tuple[bool, str]:
    """
    Checks if a user can download media.
    Admins & Premium users have unlimited access.
    Normal users are restricted to 1 download per 24 hours.
    """
    if telegram_id in config.ADMIN_IDS:
        return True, "admin"

    user = get_or_create_user(telegram_id, "User", None)

    if user.get("is_premium"):
        return True, "premium"

    if user.get("daily_yt_downloads", 0) < 1:
        return True, "free"

    return False, "limit_reached"


def record_successful_download(telegram_id: int, action_type: str = "youtube"):
    """
    Increments daily and total download counters, updates last download timestamp,
    and updates overall system statistics.
    """
    now = datetime.now(timezone.utc).isoformat()
    user = get_or_create_user(telegram_id, "User", None)

    # 1. Update user download counters
    new_daily = user.get("daily_yt_downloads", 0) + 1
    new_total = user.get("total_downloads", 0) + 1

    supabase.table("users").update({
        "daily_yt_downloads": new_daily,
        "total_downloads": new_total,
        "last_download_date": now
    }).eq("telegram_id", telegram_id).execute()

    # 2. Increment action statistics counter
    try:
        stats_res = supabase.table("statistics").select("count").eq("action_type", action_type).execute()
        if stats_res.data:
            current_count = stats_res.data[0].get("count", 0)
            supabase.table("statistics").update({
                "count": current_count + 1,
                "updated_at": now
            }).eq("action_type", action_type).execute()
    except Exception as e:
        print(f"Error updating statistics: {e}")

# ---------------------------------------------------------
# Payment & Premium Management
# ---------------------------------------------------------

def create_payment_request(
    user_id: int,
    registered_name: str,
    gender: str,
    payment_method: str,
    receipt_file_id: str
) -> Dict[str, Any]:
    """Creates a new pending payment record in Supabase."""
    payment_data = {
        "user_id": user_id,
        "registered_name": registered_name,
        "gender": gender,
        "payment_method": payment_method,
        "receipt_file_id": receipt_file_id,
        "status": "pending"
    }
    res = supabase.table("payments").insert(payment_data).execute()
    return res.data[0]


def get_payment_by_id(payment_id: str) -> Optional[Dict[str, Any]]:
    """Retrieves payment record by UUID."""
    res = supabase.table("payments").select("*").eq("id", payment_id).execute()
    return res.data[0] if res.data else None


def approve_payment(payment_id: str, admin_id: int) -> Optional[Dict[str, Any]]:
    """
    Approves payment and grants 30 days premium to the user.
    Prevents double approval if already handled.
    """
    payment = get_payment_by_id(payment_id)
    if not payment or payment.get("status") != "pending":
        return None  # Already handled or invalid

    now = datetime.now(timezone.utc)
    expiry_date = (now + timedelta(days=30)).isoformat()

    # 1. Update Payment Status
    supabase.table("payments").update({
        "status": "approved",
        "handled_by": str(admin_id)
    }).eq("id", payment_id).execute()

    # 2. Grant Premium to User
    user_id = payment["user_id"]
    supabase.table("users").update({
        "is_premium": True,
        "premium_expiry": expiry_date
    }).eq("telegram_id", user_id).execute()

    return payment


def discard_payment(payment_id: str, admin_id: int, reason: str) -> Optional[Dict[str, Any]]:
    """
    Rejects payment and logs administrative reason.
    """
    payment = get_payment_by_id(payment_id)
    if not payment or payment.get("status") != "pending":
        return None

    res = supabase.table("payments").update({
        "status": "discarded",
        "handled_by": str(admin_id),
        "reject_reason": reason
    }).eq("id", payment_id).execute()

    return res.data[0] if res.data else None

# ---------------------------------------------------------
# Statistics & Export Functions
# ---------------------------------------------------------

def get_system_analytics() -> Dict[str, Any]:
    """
    Fetches stats for Admin Dashboard & Status.
    """
    all_users = supabase.table("users").select("is_premium, role").execute().data or []
    total_users = len(all_users)
    premium_users = sum(1 for u in all_users if u.get("is_premium"))
    normal_users = total_users - premium_users

    stats_res = supabase.table("statistics").select("*").execute().data or []
    platform_stats = {item["action_type"]: item["count"] for item in stats_res}

    return {
        "total_users": total_users,
        "premium_users": premium_users,
        "normal_users": normal_users,
        "platform_stats": platform_stats
    }


def get_users_for_export(filter_type: str = "all") -> List[Dict[str, Any]]:
    """Retrieves user data formatted for CSV Export."""
    if filter_type == "premium":
        return supabase.table("users").select("*").eq("is_premium", True).execute().data or []
    elif filter_type == "discarded":
        # Get users who had payments rejected
        payments = supabase.table("payments").select("user_id, reject_reason").eq("status", "discarded").execute().data or []
        user_ids = [p["user_id"] for p in payments]
        if not user_ids:
            return []
        return supabase.table("users").select("*").in_("telegram_id", user_ids).execute().data or []
    else:
        return supabase.table("users").select("*").execute().data or []


def check_and_get_expired_premium_users() -> List[int]:
    """
    Cron helper to find users whose premium expired recently to send notifications.
    """
    now = datetime.now(timezone.utc).isoformat()
    # Find users marked premium but expiry passed
    res = supabase.table("users").select("telegram_id").eq("is_premium", True).lt("premium_expiry", now).execute()
    expired_ids = [u["telegram_id"] for u in res.data or []]

    # Revert status
    if expired_ids:
        supabase.table("users").update({
            "is_premium": False,
            "premium_expiry": None
        }).in_("telegram_id", expired_ids).execute()

    return expired_ids