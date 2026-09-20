import math
from datetime import datetime, timezone

def format_bytes(size_in_bytes: int) -> str:
    """Converts raw byte sizes to human-readable MB / GB string."""
    if size_in_bytes == 0:
        return "0 MB"
    size_name = ("B", "KB", "MB", "GB", "TB")
    i = int(math.floor(math.log(size_in_bytes, 1024)))
    p = math.pow(1024, i)
    s = round(size_in_bytes / p, 2)
    return f"{s} {size_name[i]}"


def format_duration(seconds: float) -> str:
    """Formats video duration in seconds to HH:MM:SS or MM:SS format."""
    if not seconds:
        return "Unknown"
    seconds = int(seconds)
    hours, remainder = divmod(seconds, 3600)
    minutes, secs = divmod(remainder, 60)
    if hours > 0:
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"
    return f"{minutes:02d}:{secs:02d}"


def generate_progress_bar(percent: float, length: int = 10) -> str:
    """Generates visual progress bar 📊 for video downloading and compressing."""
    filled_length = int(length * percent // 100)
    bar = '█' * filled_length + '░' * (length - filled_length)
    return f"[{bar}] {percent:.1f}%"


def calculate_days_remaining(expiry_iso_string: str) -> int:
    """Calculates remaining active subscription days for premium users."""
    if not expiry_iso_string:
        return 0
    now = datetime.now(timezone.utc)
    expiry_dt = datetime.fromisoformat(expiry_iso_string.replace("Z", "+00:00"))
    delta = expiry_dt - now
    return max(0, delta.days)