import os
import asyncio
from typing import Dict, Any, Optional
import yt_dlp

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DOWNLOAD_DIR = os.path.join(BASE_DIR, "downloads")
os.makedirs(DOWNLOAD_DIR, exist_ok=True)


def get_base_ydl_options() -> dict:
    """Base yt-dlp options shared by all supported platforms."""
    return {
        'quiet': True,
        'no_warnings': True,
        'noplaylist': True,
        'geo_bypass': True,
        'nocheckcertificate': True,
        'source_address': '0.0.0.0',
        'js_runtimes': {'node': {}},
    }


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

    try:
        path = await asyncio.to_thread(_download, ydl_opts)
        if os.path.exists(path):
            return path
    except Exception as e:
        print(f"Primary format failed: {e}. Retrying with universal fallback...")
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
            pass