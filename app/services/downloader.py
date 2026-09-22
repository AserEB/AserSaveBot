import os
import glob
import re
import asyncio
import urllib.request
import json
import subprocess
from typing import Dict, Any, Optional, List
import yt_dlp

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DOWNLOAD_DIR = os.path.join(BASE_DIR, "downloads")
os.makedirs(DOWNLOAD_DIR, exist_ok=True)


def resolve_url(url: str) -> str:
    """Follows redirects for short links and cleans tracking parameters."""
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

    if "pinterest.com/pin/" in target_url:
        match = re.search(r'(https?://[^\s]+/pin/\d+)', target_url)
        if match:
            target_url = match.group(1) + "/"

    if "tiktok.com" in target_url:
        target_url = target_url.split("?")[0]

    return target_url


def prepare_cookie_file() -> Optional[str]:
    """Prepares netscape cookie file from Heroku Environment variable or local file."""
    cookie_path = '/tmp/youtube_cookies.txt'
    env_cookie = os.getenv('YOUTUBE_COOKIES_TXT')
    local_cookie = os.path.join(BASE_DIR, "cookies.txt")

    if env_cookie and len(env_cookie.strip()) > 30:
        try:
            content = env_cookie.strip()
            if not content.startswith('# Netscape'):
                content = '# Netscape HTTP Cookie File\n' + content
            with open(cookie_path, 'w', encoding='utf-8') as f:
                f.write(content)
            return cookie_path
        except Exception as e:
            print(f"Error writing env cookie: {e}")

    if os.path.exists(local_cookie) and os.path.getsize(local_cookie) > 30:
        return local_cookie

    return None


def get_ydl_options_for_url(url: str) -> dict:
    """Provides optimized yt-dlp configurations with authentication cookies."""
    options = {
        'quiet': True,
        'no_warnings': True,
        'noplaylist': True,
        'geo_bypass': True,
        'nocheckcertificate': True,
        'http_headers': {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36',
            'Accept-Language': 'en-US,en;q=0.9',
        }
    }

    cookie_file = prepare_cookie_file()
    if cookie_file:
        options['cookiefile'] = cookie_file

    if any(domain in url for domain in ["youtube.com", "youtu.be"]):
        options['extractor_args'] = {
            'youtube': {
                'player_client': ['ios', 'android', 'mweb']
            }
        }
    return options


async def extract_media_info(url: str) -> Optional[Dict[str, Any]]:
    """Extracts video metadata safely."""
    real_url = resolve_url(url)
    ydl_opts = get_ydl_options_for_url(real_url)
    ydl_opts['skip_download'] = True

    def _extract():
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(real_url, download=False)
            if not info:
                return None

            thumb = info.get("thumbnail")
            if not thumb and info.get("thumbnails"):
                thumb = info.get("thumbnails")[-1].get("url")

            return {
                "id": info.get("id"),
                "title": info.get("title", "Media Video"),
                "duration": info.get("duration", 0),
                "thumbnail": thumb,
                "platform": "youtube" if any(domain in real_url for domain in ["youtube.com", "youtu.be"]) else "media"
            }

    try:
        return await asyncio.to_thread(_extract)
    except Exception as e:
        print(f"Extraction error: {repr(e)}")
        # Default metadata fallback
        return {
            "id": "media_id",
            "title": "Downloaded Video",
            "duration": 0,
            "thumbnail": None,
            "platform": "youtube" if any(domain in real_url for domain in ["youtube.com", "youtu.be"]) else "media"
        }


async def search_youtube_videos(query: str, max_results: int = 5) -> List[Dict[str, Any]]:
    """Performs quick YouTube keyword search."""
    search_spec = f"ytsearch{max_results}:{query}"
    ydl_opts = {
        'quiet': True,
        'no_warnings': True,
        'extract_flat': True,
        'skip_download': True,
    }

    def _search():
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(search_spec, download=False)
            return info.get('entries', []) if info else []

    try:
        entries = await asyncio.to_thread(_search)
        results = []
        for entry in entries:
            if not entry:
                continue
            video_url = entry.get('url') or f"https://www.youtube.com/watch?v={entry.get('id')}"
            thumb = entry.get('thumbnail')
            if not thumb and entry.get('thumbnails'):
                thumb = entry.get('thumbnails')[-1].get('url')
            results.append({
                "id": entry.get("id"),
                "title": entry.get("title", "YouTube Video"),
                "url": video_url,
                "duration": entry.get("duration", 0),
                "thumbnails": entry.get("thumbnails", []),
                "thumbnail": thumb,
                "channel": entry.get("uploader", "YouTube Creator")
            })
        return results
    except Exception as e:
        print(f"YouTube search error: {e}")
        return []


async def download_media_file(url: str, format_spec: str, custom_filename: str) -> Optional[str]:
    """Downloads media file via optimized yt-dlp process with cookie support."""
    real_url = resolve_url(url)
    base_name = os.path.splitext(custom_filename)[0]
    outtmpl = os.path.join(DOWNLOAD_DIR, f"{base_name}.%(ext)s")
    is_audio = "mp3" in custom_filename.lower() or "mp3" in format_spec.lower()

    cmd = [
        "yt-dlp",
        "--no-warnings",
        "--geo-bypass",
        "--no-check-certificates",
        "--user-agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
        "-o", outtmpl
    ]

    # Cookie Injection
    cookie_file = prepare_cookie_file()
    if cookie_file:
        cmd.extend(["--cookies", cookie_file])

    if any(domain in real_url for domain in ["youtube.com", "youtu.be"]):
        cmd.extend(["--extractor-args", "youtube:player_client=ios,android,mweb"])

    if is_audio:
        cmd.extend(["-x", "--audio-format", "mp3", "--audio-quality", "192K"])
    else:
        cmd.extend(["-f", "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/b/best", "--merge-output-format", "mp4"])

    cmd.append(real_url)

    def _run_sub():
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
            print(f"yt-dlp output: {result.stdout}")
            if result.returncode != 0:
                print(f"yt-dlp error: {result.stderr}")
            return result.returncode == 0
        except Exception as ex:
            print(f"Subprocess exception: {ex}")
            return False

    success = await asyncio.to_thread(_run_sub)
    if success:
        matching = glob.glob(os.path.join(DOWNLOAD_DIR, f"{base_name}.*"))
        for f in matching:
            if not f.endswith(".part") and not f.endswith(".ytdl"):
                return f

    return None


def cleanup_file(file_path: Optional[str]):
    """Safely removes temporary files."""
    if file_path and os.path.exists(file_path):
        try:
            os.remove(file_path)
        except Exception:
            pass