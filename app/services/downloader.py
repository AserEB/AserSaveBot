import os
import glob
import re
import asyncio
import urllib.request
import traceback
import subprocess
from typing import Dict, Any, Optional, List
import yt_dlp

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DOWNLOAD_DIR = os.path.join(BASE_DIR, "downloads")
os.makedirs(DOWNLOAD_DIR, exist_ok=True)


def resolve_url(url: str) -> str:
    """Follows redirects for short links (pin.it, vt.tiktok.com) and cleans tracking params."""
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

    # Clean Pinterest tracking parameters and extra paths (/sent/?invite_code=...)
    if "pinterest.com/pin/" in target_url:
        match = re.search(r'(https?://[^\s]+/pin/\d+)', target_url)
        if match:
            target_url = match.group(1) + "/"

    if "tiktok.com" in target_url or "instagram.com" in target_url:
        target_url = target_url.split("?")[0]

    return target_url


def download_pinterest_image_fallback(url: str, dest_path: str) -> bool:
    """Fallback helper to download Pinterest photos when yt-dlp finds no video formats."""
    try:
        req = urllib.request.Request(
            url,
            headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36'}
        )
        with urllib.request.urlopen(req, timeout=15) as response:
            html = response.read().decode('utf-8', errors='ignore')
            match = re.search(r'<meta\s+property="og:image"\s+content="([^"]+)"', html) or \
                    re.search(r'<meta\s+name="og:image"\s+content="([^"]+)"', html)
            
            if match:
                img_url = match.group(1)
                # Upgrade image quality to original resolution if possible
                img_url = re.sub(r'/(236x|474x|736x)/', '/originals/', img_url)
                
                img_req = urllib.request.Request(
                    img_url,
                    headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
                )
                with urllib.request.urlopen(img_req, timeout=20) as img_resp:
                    with open(dest_path, 'wb') as f:
                        f.write(img_resp.read())
                return os.path.exists(dest_path) and os.path.getsize(dest_path) > 1000
    except Exception as e:
        print(f"Pinterest image fallback error: {e}")
    return False


def get_ydl_options_for_url(url: str) -> dict:
    """Provides optimized yt-dlp configurations using clean cookies."""
    options = {
        'quiet': True,
        'no_warnings': True,
        'noplaylist': True,
        'geo_bypass': True,
        'nocheckcertificate': True,
        'source_address': '0.0.0.0',
        'http_headers': {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36',
            'Accept-Language': 'en-US,en;q=0.9',
        }
    }

    if any(domain in url for domain in ["youtube.com", "youtu.be"]):
        options['extractor_args'] = {
            'youtube': {
                'player_client': ['mweb', 'android', 'web']
            }
        }

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
            except Exception as e:
                print(f"Error writing env cookie: {e}")
        elif os.path.exists(local_cookie) and os.path.getsize(local_cookie) > 30:
            options['cookiefile'] = local_cookie

    elif "tiktok.com" in url:
        options['extractor_args'] = {
            'tiktok': {
                'api_hostname': 'api22-normal-c-useast2a.tiktokv.com'
            }
        }

    return options


async def extract_media_info(url: str) -> Optional[Dict[str, Any]]:
    """Extracts metadata safely with process=False to bypass format selection."""
    real_url = resolve_url(url)
    ydl_opts = get_ydl_options_for_url(real_url)
    ydl_opts['skip_download'] = True
    ydl_opts['check_formats'] = False

    is_yt = any(domain in real_url for domain in ["youtube.com", "youtu.be"])

    def _extract():
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(real_url, download=False, process=False)
            if not info:
                return None

            if 'entries' in info and len(info['entries']) > 0:
                info = info['entries'][0]

            thumb = info.get("thumbnail")
            if not thumb and info.get("thumbnails"):
                thumbs = [t.get("url") for t in info.get("thumbnails") if t.get("url")]
                if thumbs:
                    thumb = thumbs[-1]

            title = info.get("title") or info.get("description", "Media Content")
            if len(title) > 60:
                title = title[:57] + "..."

            return {
                "id": info.get("id", "media_id"),
                "title": title,
                "duration": info.get("duration", 0),
                "thumbnail": thumb,
                "platform": "youtube" if is_yt else "media"
            }

    try:
        return await asyncio.to_thread(_extract)
    except Exception as e:
        print(f"Extraction error: {repr(e)}")
        return {
            "id": "media_id",
            "title": "Media Content",
            "duration": 0,
            "thumbnail": None,
            "platform": "youtube" if is_yt else "media"
        }


async def search_youtube_videos(query: str, max_results: int = 5) -> List[Dict[str, Any]]:
    """Performs quick YouTube keyword search returning top metadata entries."""
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
        print(f"YouTube search error for query '{query}': {e}")
        return []


async def download_media_file(url: str, format_spec: str, custom_filename: str) -> Optional[str]:
    """Downloads media file securely using system yt-dlp command-line subprocess to avoid Python API format locks."""
    real_url = resolve_url(url)
    base_name = os.path.splitext(custom_filename)[0]
    outtmpl = os.path.join(DOWNLOAD_DIR, f"{base_name}.%(ext)s")

    is_audio = "mp3" in format_spec.lower() or "mp3" in custom_filename.lower()

    # Build yt-dlp command with valid flags
    cmd = [
        "yt-dlp",
        "--no-warnings",
        "--geo-bypass",
        "--no-check-certificates",
        "--user-agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
        "-o", outtmpl
    ]

    # Add specific extractor options for YouTube and TikTok in CLI command
    if any(domain in real_url for domain in ["youtube.com", "youtu.be"]):
        cmd.extend(["--extractor-args", "youtube:player_client=mweb,android,web"])
    elif "tiktok.com" in real_url:
        cmd.extend(["--extractor-args", "tiktok:api_hostname=api22-normal-c-useast2a.tiktokv.com"])

    # Cookie check
    env_cookie = os.getenv('YOUTUBE_COOKIES_TXT')
    local_cookie = os.path.join(BASE_DIR, "cookies.txt")
    cookie_file_to_use = None

    if env_cookie and len(env_cookie.strip()) > 30:
        cookie_path = '/tmp/youtube_cookies.txt'
        try:
            content = env_cookie.strip()
            if not content.startswith('# Netscape'):
                content = '# Netscape HTTP Cookie File\n' + content
            with open(cookie_path, 'w', encoding='utf-8') as f:
                f.write(content)
            cookie_file_to_use = cookie_path
        except Exception:
            pass
    elif os.path.exists(local_cookie) and os.path.getsize(local_cookie) > 30:
        cookie_file_to_use = local_cookie

    if cookie_file_to_use:
        cmd.extend(["--cookies", cookie_file_to_use])

    if is_audio:
        cmd.extend(["-x", "--audio-format", "mp3", "--audio-quality", "192K"])
    else:
        # Format selection supporting YouTube & Instagram audio/video merge
        cmd.extend(["-f", "bv*+ba/b/best", "--merge-output-format", "mp4"])

    cmd.append(real_url)

    def _run_sub():
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
            print(f"Subprocess stdout: {result.stdout}")
            print(f"Subprocess stderr: {result.stderr}")
            return result.returncode == 0
        except Exception as ex:
            print(f"Subprocess exception: {ex}")
            return False

    success = await asyncio.to_thread(_run_sub)

    # Fallback to download Pinterest Photo if yt-dlp fails (e.g. No video formats found)
    if not success and "pinterest" in real_url:
        fallback_img_path = os.path.join(DOWNLOAD_DIR, f"{base_name}.jpg")
        img_success = await asyncio.to_thread(download_pinterest_image_fallback, real_url, fallback_img_path)
        if img_success:
            return fallback_img_path

    if not success:
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
    """Safely removes temporary media files from disk after processing/sending."""
    if file_path and os.path.exists(file_path):
        try:
            os.remove(file_path)
        except Exception:
            pass