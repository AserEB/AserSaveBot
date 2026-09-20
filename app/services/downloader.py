import os
import asyncio
from typing import Dict, Any, Optional
import yt_dlp

# Directory for storing temporary video/audio files
DOWNLOAD_DIR = "downloads"
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

# Path to YouTube Cookies File
COOKIE_FILE = "cookies.txt"


def get_base_ydl_options() -> dict:
    """Base yt-dlp options configured for maximum YouTube compatibility."""
    opts = {
        'quiet': True,
        'no_warnings': True,
        'noplaylist': True,
        # 'mweb' and 'android' clients provide the most stable video formats without format-unavailable errors
        'extractor_args': {
            'youtube': {
                'player_client': ['mweb', 'android', 'web'],
            }
        }
    }
    if os.path.exists(COOKIE_FILE):
        opts['cookiefile'] = COOKIE_FILE
    return opts


async def extract_media_info(url: str) -> Optional[Dict[str, Any]]:
    """Extracts metadata without downloading."""
    ydl_opts = get_base_ydl_options()
    ydl_opts['skip_download'] = True

    def _extract():
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            return ydl.extract_info(url, download=False)

    try:
        return await asyncio.to_thread(_extract)
    except Exception as e:
        print(f"Error extracting metadata from {url}: {e}")
        return None


async def download_media_file(
    url: str, 
    format_spec: str, 
    custom_filename: str
) -> Optional[str]:
    """Downloads media file using yt-dlp with automatic format fallbacks."""
    output_path = os.path.join(DOWNLOAD_DIR, custom_filename)
    ydl_opts = get_base_ydl_options()
    ydl_opts['outtmpl'] = output_path
    ydl_opts['overwrites'] = True

    # 1. Configure MP3 audio extraction if requested
    if "mp3" in format_spec.lower() or "mp3" in custom_filename.lower():
        ydl_opts['format'] = 'bestaudio/best'
        ydl_opts['postprocessors'] = [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': '192',
        }]
    elif "1080" in format_spec:
        ydl_opts['format'] = 'bestvideo[height<=1080]+bestaudio/best[height<=1080]/best'
    elif "720" in format_spec:
        ydl_opts['format'] = 'bestvideo[height<=720]+bestaudio/best[height<=720]/best'
    elif "480" in format_spec:
        ydl_opts['format'] = 'bestvideo[height<=480]+bestaudio/best[height<=480]/best'
    else:
        ydl_opts['format'] = 'bestvideo+bestaudio/best'

    def _download(opts):
        with yt_dlp.YoutubeDL(opts) as ydl:
            ydl.download([url])
        return output_path

    # Try downloading with primary format selection
    try:
        path = await asyncio.to_thread(_download, ydl_opts)
        if os.path.exists(path):
            return path
    except Exception as e:
        print(f"Primary format failed: {e}. Retrying with absolute fallback...")
        
        # Absolute Fallback attempt
        fallback_opts = get_base_ydl_options()
        fallback_opts['outtmpl'] = output_path
        fallback_opts['overwrites'] = True
        fallback_opts['format'] = 'best'
        
        try:
            path = await asyncio.to_thread(_download, fallback_opts)
            if os.path.exists(path):
                return path
        except Exception as fe:
            print(f"Fallback failed: {fe}")
            return None

    base_path = os.path.splitext(output_path)[0]
    if os.path.exists(f"{base_path}.mp3"):
        return f"{base_path}.mp3"
        
    return None


def cleanup_file(file_path: Optional[str]):
    """Safely removes temporary media files from disk after processing/sending."""
    if file_path and os.path.exists(file_path):
        try:
            os.remove(file_path)
        except Exception as e:
            print(f"Error removing temp file {file_path}: {e}")