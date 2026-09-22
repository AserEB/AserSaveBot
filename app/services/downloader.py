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

# Currently Active Invidious & Piped Instances
INVIDIOUS_INSTANCES = [
    "https://inv.tux.pizza",
    "https://invidious.nerdvpn.de",
    "https://vid.puffyan.us",
    "https://invidious.drgns.space",
    "https://invidious.projectsegfau.lt"
]

PIPED_INSTANCES = [
    "https://pipedapi.adminforge.de",
    "https://pipedapi.tokhmi.xyz",
    "https://pipedapi.rinuo.cc",
    "https://pipedapi.astral.ne.jp"
]


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


def extract_youtube_id(url: str) -> Optional[str]:
    """Extracts YouTube 11-character video ID."""
    match = re.search(r'(?:v=|\/|be\/|shorts\/)([0-9A-Za-z_-]{11})', url)
    return match.group(1) if match else None


def download_youtube_via_api(video_id: str, quality: str, dest_path: str) -> bool:
    """Attempts YouTube download via active Invidious APIs first, then Piped APIs."""
    is_audio = quality.lower() == "mp3"

    # Strategy A: Try Invidious Instances
    for instance in INVIDIOUS_INSTANCES:
        try:
            api_url = f"{instance}/api/v1/videos/{video_id}"
            req = urllib.request.Request(
                api_url,
                headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
            )
            with urllib.request.urlopen(req, timeout=8) as response:
                if response.status != 200:
                    continue
                data = json.loads(response.read().decode('utf-8'))

            selected_url = None

            if is_audio:
                adaptive = data.get("adaptiveFormats", [])
                audio_formats = [f for f in adaptive if str(f.get("type", "")).startswith("audio/")]
                if audio_formats:
                    selected_url = audio_formats[0].get("url")
            else:
                format_streams = data.get("formatStreams", [])
                target_q = quality if quality.isdigit() else "360"
                
                # Match requested quality
                for stream in format_streams:
                    if target_q in str(stream.get("qualityLabel", "")):
                        selected_url = stream.get("url")
                        break
                
                if not selected_url and format_streams:
                    selected_url = format_streams[0].get("url")

            if selected_url:
                dl_req = urllib.request.Request(
                    selected_url,
                    headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
                )
                with urllib.request.urlopen(dl_req, timeout=120) as stream_resp:
                    with open(dest_path, 'wb') as f:
                        while chunk := stream_resp.read(1024 * 64):
                            f.write(chunk)

                if os.path.exists(dest_path) and os.path.getsize(dest_path) > 10000:
                    print(f"Successfully downloaded via Invidious API ({instance})")
                    return True
        except Exception as e:
            print(f"Invidious instance {instance} failed: {e}")
            continue

    # Strategy B: Fallback to Active Piped Instances
    for instance in PIPED_INSTANCES:
        try:
            api_url = f"{instance}/streams/{video_id}"
            req = urllib.request.Request(
                api_url,
                headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
            )
            with urllib.request.urlopen(req, timeout=8) as response:
                if response.status != 200:
                    continue
                data = json.loads(response.read().decode('utf-8'))

            selected_url = None

            if is_audio:
                audio_streams = data.get("audioStreams", [])
                if audio_streams:
                    selected_url = audio_streams[0].get("url")
            else:
                video_streams = data.get("videoStreams", [])
                combined = [s for s in video_streams if s.get("videoOnly") is False]
                if combined:
                    selected_url = combined[0].get("url")
                elif video_streams:
                    selected_url = video_streams[0].get("url")

            if selected_url:
                dl_req = urllib.request.Request(
                    selected_url,
                    headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
                )
                with urllib.request.urlopen(dl_req, timeout=120) as stream_resp:
                    with open(dest_path, 'wb') as f:
                        while chunk := stream_resp.read(1024 * 64):
                            f.write(chunk)

                if os.path.exists(dest_path) and os.path.getsize(dest_path) > 10000:
                    print(f"Successfully downloaded via Piped API ({instance})")
                    return True
        except Exception as e:
            print(f"Piped instance {instance} failed: {e}")
            continue

    return False


async def extract_media_info(url: str) -> Optional[Dict[str, Any]]:
    """Extracts video metadata using Invidious/Piped API for YouTube or yt-dlp for others."""
    real_url = resolve_url(url)
    yt_id = extract_youtube_id(real_url)

    if yt_id:
        for instance in INVIDIOUS_INSTANCES:
            try:
                api_url = f"{instance}/api/v1/videos/{yt_id}"
                req = urllib.request.Request(
                    api_url,
                    headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
                )
                with urllib.request.urlopen(req, timeout=6) as response:
                    if response.status == 200:
                        data = json.loads(response.read().decode('utf-8'))
                        return {
                            "id": yt_id,
                            "title": data.get("title", "YouTube Video"),
                            "duration": data.get("lengthSeconds", 0),
                            "thumbnail": f"https://img.youtube.com/vi/{yt_id}/hqdefault.jpg",
                            "platform": "youtube"
                        }
            except Exception:
                continue

        return {
            "id": yt_id,
            "title": "YouTube Video",
            "duration": 0,
            "thumbnail": f"https://img.youtube.com/vi/{yt_id}/hqdefault.jpg",
            "platform": "youtube"
        }

    # Non-YouTube Platforms (TikTok, Facebook, Instagram, Pinterest)
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
    """Downloads media files via API System for YouTube, yt-dlp for others."""
    real_url = resolve_url(url)
    yt_id = extract_youtube_id(real_url)
    base_name = os.path.splitext(custom_filename)[0]

    quality_tag = "360"
    for q in ["1080", "720", "480", "360", "240", "144"]:
        if q in custom_filename or q in format_spec:
            quality_tag = q
            break

    is_audio = "mp3" in custom_filename.lower() or "mp3" in format_spec.lower()
    if is_audio:
        quality_tag = "mp3"

    ext = "mp3" if is_audio else "mp4"
    dest_path = os.path.join(DOWNLOAD_DIR, f"{base_name}.{ext}")

    # 1. YouTube Multi-API Extraction
    if yt_id:
        print(f"Downloading YouTube video {yt_id} via API Network...")
        success = await asyncio.to_thread(download_youtube_via_api, yt_id, quality_tag, dest_path)
        if success and os.path.exists(dest_path):
            return dest_path

    # 2. Non-YouTube platforms (TikTok, FB, Insta, Pinterest) via yt-dlp
    outtmpl = os.path.join(DOWNLOAD_DIR, f"{base_name}.%(ext)s")
    cmd = [
        "yt-dlp",
        "--no-warnings",
        "--geo-bypass",
        "--no-check-certificates",
        "-o", outtmpl
    ]

    if is_audio:
        cmd.extend(["-x", "--audio-format", "mp3", "--audio-quality", "192K"])
    else:
        cmd.extend(["-f", "b/best", "--merge-output-format", "mp4"])

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