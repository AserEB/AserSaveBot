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
            with urllib.request.urlopen(req, timeout=5) as response:
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


def extract_youtube_id(url: str) -> Optional[str]:
    """Extracts YouTube 11-character video ID."""
    match = re.search(r'(?:v=|\/|be\/|shorts\/)([0-9A-Za-z_-]{11})', url)
    return match.group(1) if match else None


async def extract_media_info(url: str) -> Optional[Dict[str, Any]]:
    """Extracts metadata instantly using YouTube oEmbed for YouTube, or yt-dlp for others."""
    real_url = resolve_url(url)
    yt_id = extract_youtube_id(real_url)

    # 1. Instant YouTube Metadata via official YouTube oEmbed API (< 0.3s)
    if yt_id:
        try:
            oembed_url = f"https://www.youtube.com/oembed?url=https://www.youtube.com/watch?v={yt_id}&format=json"
            req = urllib.request.Request(
                oembed_url,
                headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
            )
            
            def _fetch_oembed():
                with urllib.request.urlopen(req, timeout=3) as response:
                    if response.status == 200:
                        return json.loads(response.read().decode('utf-8'))
                return None

            data = await asyncio.to_thread(_fetch_oembed)
            if data:
                return {
                    "id": yt_id,
                    "title": data.get("title", "YouTube Video"),
                    "duration": 0,
                    "thumbnail": f"https://img.youtube.com/vi/{yt_id}/hqdefault.jpg",
                    "platform": "youtube"
                }
        except Exception as e:
            print(f"oEmbed fetch error: {e}")

        # Fallback instant info for YouTube
        return {
            "id": yt_id,
            "title": "YouTube Video",
            "duration": 0,
            "thumbnail": f"https://img.youtube.com/vi/{yt_id}/hqdefault.jpg",
            "platform": "youtube"
        }

    # 2. Non-YouTube Platforms (TikTok, Facebook, Instagram, Pinterest)
    ydl_opts = {
        'quiet': True,
        'no_warnings': True,
        'skip_download': True,
        'geo_bypass': True,
    }

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
                "platform": "media"
            }

    try:
        return await asyncio.to_thread(_extract)
    except Exception as e:
        print(f"General extraction error: {e}")
        return None


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
    """Downloads media files using tv/android_embedded clients for YouTube and direct yt-dlp for others."""
    real_url = resolve_url(url)
    yt_id = extract_youtube_id(real_url)
    base_name = os.path.splitext(custom_filename)[0]
    outtmpl = os.path.join(DOWNLOAD_DIR, f"{base_name}.%(ext)s")

    is_audio = "mp3" in custom_filename.lower() or "mp3" in format_spec.lower()

    cmd = [
        "yt-dlp",
        "--no-warnings",
        "--geo-bypass",
        "--no-check-certificates",
        "-o", outtmpl
    ]

    if yt_id:
        # Bypass YouTube Bot block on Heroku using TV & Embedded Android Clients
        cmd.extend([
            "--extractor-args", "youtube:player_client=tv,android_embedded,ios"
        ])

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