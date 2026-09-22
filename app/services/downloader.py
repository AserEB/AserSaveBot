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

    if "pinterest.com/pin/" in target_url:
        match = re.search(r'(https?://[^\s]+/pin/\d+)', target_url)
        if match:
            target_url = match.group(1) + "/"

    if "tiktok.com" in target_url:
        target_url = target_url.split("?")[0]

    return target_url


def download_via_cobalt_api(url: str, quality: str, dest_path: str) -> bool:
    """Uses open-source Cobalt API to bypass YouTube Datacenter/Heroku IP restrictions."""
    try:
        cobalt_url = "https://api.cobalt.tools/api/json"
        
        # Map qualities to Cobalt formats
        video_quality = "720"
        if quality in ["1080", "720", "480", "360", "240", "144"]:
            video_quality = quality

        is_audio = quality.lower() == "mp3"

        payload = {
            "url": url,
            "videoQuality": video_quality,
            "downloadMode": "audio" if is_audio else "auto",
            "audioFormat": "mp3" if is_audio else "best"
        }

        req = urllib.request.Request(
            cobalt_url,
            data=json.dumps(payload).encode('utf-8'),
            headers={
                'Accept': 'application/json',
                'Content-Type': 'application/json',
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'
            },
            method='POST'
        )

        with urllib.request.urlopen(req, timeout=30) as response:
            res_data = json.loads(response.read().decode('utf-8'))
            
            download_link = None
            if res_data.get("status") in ["tunnel", "redirect"]:
                download_link = res_data.get("url")
            elif res_data.get("status") == "picker":
                picker = res_data.get("picker", [])
                if picker:
                    download_link = picker[0].get("url")

            if download_link:
                dl_req = urllib.request.Request(
                    download_link,
                    headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
                )
                with urllib.request.urlopen(dl_req, timeout=120) as media_resp:
                    with open(dest_path, 'wb') as f:
                        f.write(media_resp.read())
                return os.path.exists(dest_path) and os.path.getsize(dest_path) > 10000
    except Exception as e:
        print(f"Cobalt API Download Exception: {e}")
    return False


def get_ydl_options_for_url(url: str) -> dict:
    """Provides optimized yt-dlp configurations."""
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

    if any(domain in url for domain in ["youtube.com", "youtu.be"]):
        options['extractor_args'] = {
            'youtube': {
                'player_client': ['ios', 'android']
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
        # Basic fallback metadata if extraction is blocked
        return {
            "id": "media_id",
            "title": "Downloaded Video",
            "duration": 0,
            "thumbnail": None,
            "platform": "youtube" if any(domain in real_url for domain in ["youtube.com", "youtu.be"]) else "media"
        }


async def search_youtube_videos(query: str, max_results: int = 5) -> List[Dict[str, Any]]:
    """Performs quick YouTube search."""
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
    """Downloads media using Cobalt API first, with yt-dlp fallback."""
    real_url = resolve_url(url)
    base_name = os.path.splitext(custom_filename)[0]
    is_audio = "mp3" in custom_filename.lower() or "mp3" in format_spec.lower()
    ext = "mp3" if is_audio else "mp4"
    dest_file_path = os.path.join(DOWNLOAD_DIR, f"{base_name}.{ext}")

    quality_tag = "720"
    for q in ["1080", "720", "480", "360", "240", "144"]:
        if q in custom_filename or q in format_spec:
            quality_tag = q
            break
    if is_audio:
        quality_tag = "mp3"

    # Step 1: Attempt Cobalt API Download (Bypasses YouTube Heroku IP Restrictions)
    print(f"Attempting Cobalt API download for: {real_url}")
    cobalt_success = await asyncio.to_thread(download_via_cobalt_api, real_url, quality_tag, dest_file_path)
    if cobalt_success and os.path.exists(dest_file_path):
        print("Cobalt API Download Successful!")
        return dest_file_path

    # Step 2: Fallback to Subprocess yt-dlp with flexible format options
    print("Cobalt API failed/skipped. Falling back to yt-dlp...")
    outtmpl = os.path.join(DOWNLOAD_DIR, f"{base_name}.%(ext)s")

    cmd = [
        "yt-dlp",
        "--no-warnings",
        "--geo-bypass",
        "--no-check-certificates",
        "--user-agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
        "-o", outtmpl
    ]

    if any(domain in real_url for domain in ["youtube.com", "youtu.be"]):
        cmd.extend(["--extractor-args", "youtube:player_client=ios,android"])

    if is_audio:
        cmd.extend(["-x", "--audio-format", "mp3", "--audio-quality", "192K"])
    else:
        # Flexible format specification for YouTube
        cmd.extend(["-f", "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/b/best", "--merge-output-format", "mp4"])

    cmd.append(real_url)

    def _run_sub():
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
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