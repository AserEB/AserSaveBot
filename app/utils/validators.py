import re
from typing import Optional

# Regular expressions for supported platforms
YOUTUBE_REGEX = r'(https?://)?(www\.)?(youtube\.com|youtu\.be)/(watch\?v=|embed/|v/|shorts/)?([a-zA-Z0-9_-]+)'
TIKTOK_REGEX = r'(https?://)?(www\.|vm\.|vt\.)?(tiktok\.com)/.*'
INSTAGRAM_REGEX = r'(https?://)?(www\.)?(instagram\.com)/(p|reel|tv)/.*'
FACEBOOK_REGEX = r'(https?://)?(www\.|web\.|m\.)?(facebook\.com|fb\.watch)/.*'
PINTEREST_REGEX = r'(https?://)?(pin\.it|[a-z]+\.pinterest\.com/pin)/.*'


def detect_platform(url: str) -> Optional[str]:
    """Detects platform type from standard URL input."""
    url = url.strip()
    if re.search(YOUTUBE_REGEX, url):
        return "youtube"
    elif re.search(TIKTOK_REGEX, url):
        return "tiktok"
    elif re.search(INSTAGRAM_REGEX, url):
        return "instagram"
    elif re.search(FACEBOOK_REGEX, url):
        return "facebook"
    elif re.search(PINTEREST_REGEX, url):
        return "pinterest"
    return None