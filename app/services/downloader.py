import os
import glob
import asyncio
import urllib.request
import traceback
from typing import Dict, Any, Optional, List
import yt_dlp

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DOWNLOAD_DIR = os.path.join(BASE_DIR, "downloads")
os.makedirs(DOWNLOAD_DIR, exist_ok=True)


def resolve_url(url: str) -> str:
    """Follows redirects for short links and cleans tracking params."""
    target_url = url.strip()
    
    if "pin.it" in target_url:
        try:
            req = urllib.request.Request(
                target_url,
                headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
            )
            with urllib.request.urlopen(req, timeout=10) as response:
                resolved = response.geturl()
                if resolved.rstrip('/') != "https://www.pinterest.com":
                    target_url = resolved
        except Exception as e:
            print(f"Error resolving Pinterest url: {e}")

    if "tiktok.com" in target_url:
        target_url = target_url.split("?")[0]

    return target_url


def get_ydl_options_for_url(url: str) -> dict:
    """Configures yt-dlp with cookie detection and mobile clients."""
    options = {
        'quiet': True,
        'no_warnings': True,
        'noplaylist': True,
        'geo_bypass': True,
        'nocheckcertificate': True,
        'source_address': '0.0.0.0',
        'http_headers': {
            'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 17_4_1 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4.1 Mobile/15E148 Safari/604.1',
            'Accept-Language': 'en-US,en;q=0.9',
        }
    }

    if any(domain in url for domain in ["youtube.com", "youtu.be"]):
        # mweb + ios bypass bot challenges reliably
        options['extractor_args'] = {
            'youtube': {
                'player_client': ['mweb', 'ios'],
                'player_skip': ['webpage', 'configs']
            }
        }

        # 1. Heroku Config Var Cookie
        env_cookie = os.getenv('YOUTUBE_COOKIES_TXT')
        local_cookie = os.path.join(BASE_DIR, "cookies.txt")

        if env_cookie and len(env_cookie.strip()) > 30:
            cookie_path = '/tmp/youtube_cookies.txt'
            try:
                content = env_cookie.strip()
                if not content.startswith('# Netscape'):
                    content = '# Netscape HTTP Cookie File\n' + content
                with open(cookie_path, 'w', encoding='utf-8') as f:
                    f.write(content)
                options['cookiefile'] = cookie_path
                print(f"[COOKIE CHECK] Loaded cookie from Heroku ENV (size: {len(content)} chars)")
            except Exception as e:
                print(f"[COOKIE CHECK] Error writing env cookie: {e}")
        elif os.path.exists(local_cookie) and os.path.getsize(local_cookie) > 30:
            options['cookiefile'] = local_cookie
            print(f"[COOKIE CHECK] Loaded cookie from local cookies.txt (size: {os.path.getsize(local_cookie)} bytes)")
        else:
            print("[COOKIE CHECK] WARNING: No valid cookie file found!")

    elif "tiktok.com" in url:
        options['extractor_args'] = {
            'tiktok': {
                'api_hostname': 'api22-normal-c-useast2a.tiktokv.com'
            }
        }

    return options


async def extract_media_info(url: str) -> Optional[Dict[str, Any]]:
    """Extracts metadata safely."""
    real_url = resolve_url(url)
    ydl_opts = get_ydl_options_for_url(real_url)
    ydl_opts['skip_download'] = True

    def _extract():
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            return ydl.extract_info(real_url, download=False)

    try:
        info = await asyncio.to_thread(_extract)
        if not info:
            return None
        return {
            "id": info.get("id"),
            "title": info.get("title", "YouTube Video"),
            "duration": info.get("duration", 0),
            "thumbnail": info.get("thumbnail"),
            "platform": "youtube"
        }
    except Exception as e:
        print(f"Extraction error: {repr(e)}")
        return None


async def download_media_file(url: str, format_spec: str, custom_filename: str) -> Optional[str]:
    """Downloads media file with strict height constraints."""
    real_url = resolve_url(url)
    base_name = os.path.splitext(custom_filename)[0]
    outtmpl_pattern = os.path.join(DOWNLOAD_DIR, f"{base_name}.%(ext)s")
    
    ydl_opts = get_ydl_options_for_url(real_url)
    ydl_opts['outtmpl'] = outtmpl_pattern
    ydl_opts['overwrites'] = True

    is_audio = "mp3" in format_spec.lower() or "mp3" in custom_filename.lower()

    if is_audio:
        ydl_opts['format'] = 'ba/b'
        ydl_opts['postprocessors'] = [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': '192',
        }]
    else:
        # Determine exact target height
        target_h = "360"
        for h in ["1080", "720", "480", "360", "240", "144"]:
            if h in format_spec:
                target_h = h
                break
        
        ydl_opts['format'] = f"best[height<={target_h}]/bestvideo[height<={target_h}]+bestaudio/best"

    def _download(opts):
        with yt_dlp.YoutubeDL(opts) as ydl:
            ydl.download([real_url])

    try:
        await asyncio.to_thread(_download, ydl_opts)
    except Exception as e:
        print(f"Download failed: {e}. Trying single stream fallback...")
        fallback_opts = get_ydl_options_for_url(real_url)
        fallback_opts['outtmpl'] = outtmpl_pattern
        fallback_opts['overwrites'] = True
        fallback_opts['format'] = 'best'
        try:
            await asyncio.to_thread(_download, fallback_opts)
        except Exception as fe:
            print(f"Fallback download failed: {fe}")
            return None

    if is_audio:
        expected_mp3 = os.path.join(DOWNLOAD_DIR, f"{base_name}.mp3")
        if os.path.exists(expected_mp3):
            return expected_mp3

    matching = glob.glob(os.path.join(DOWNLOAD_DIR, f"{base_name}.*"))
    for f in matching:
        if not f.endswith(".part") and not f.endswith(".ytdl"):
            return f

    return None


def cleanup_file(file_path: Optional[str]):
    """Removes temporary files."""
    if file_path and os.path.exists(file_path):
        try:
            os.remove(file_path)
        except Exception:
            pass