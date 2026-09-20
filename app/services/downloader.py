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
    """Returns base yt-dlp configurations with YouTube bot-bypass headers and cookies."""
    opts = {
        'quiet': True,
        'no_warnings': True,
        'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
        'extractor_args': {
            'youtube': {
                'player_client': ['android', 'ios', 'web'],
            }
        }
    }
    # Attach cookiefile if present
    if os.path.exists(COOKIE_FILE):
        opts['cookiefile'] = COOKIE_FILE
    return opts


async def extract_media_info(url: str) -> Optional[Dict[str, Any]]:
    """Extracts video metadata without downloading the file."""
    ydl_opts = get_base_ydl_options()
    ydl_opts.update({
        'skip_download': True,
        'noplaylist': True,
        'extract_flat': False,
        # Flexible format selector to avoid 'Requested format is not available' error
        'format': 'best/bestvideo+bestaudio/all',
    })

    def _extract():
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            return ydl.extract_info(url, download=False)

    try:
        info = await asyncio.to_thread(_extract)
        return info
    except Exception as e:
        print(f"Error extracting metadata from {url}: {e}")
        return None


async def download_media_file(
    url: str, 
    format_spec: str, 
    custom_filename: str
) -> Optional[str]:
    """Downloads media file using yt-dlp based on requested format with fallbacks."""
    output_path = os.path.join(DOWNLOAD_DIR, custom_filename)
    
    ydl_opts = get_base_ydl_options()

    # Add flexible resolution fallbacks
    if "1080" in format_spec:
        format_spec = "bestvideo[height<=1080]+bestaudio/bestvideo[height<=1080]/best[height<=1080]/best"
    elif "720" in format_spec:
        format_spec = "bestvideo[height<=720]+bestaudio/bestvideo[height<=720]/best[height<=720]/best"
    elif "480" in format_spec:
        format_spec = "bestvideo[height<=480]+bestaudio/bestvideo[height<=480]/best[height<=480]/best"

    ydl_opts['format'] = format_spec
    ydl_opts['outtmpl'] = output_path
    ydl_opts['overwrites'] = True

    # If audio extraction is requested
    if format_spec == "bestaudio/best" or "mp3" in custom_filename.lower():
        ydl_opts['postprocessors'] = [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': '192',
        }]

    def _download():
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])
        return output_path

    try:
        path = await asyncio.to_thread(_download)
        
        if not os.path.exists(path):
            base_path = os.path.splitext(path)[0]
            if os.path.exists(f"{base_path}.mp3"):
                return f"{base_path}.mp3"
            
        return path if os.path.exists(path) else None
    except Exception as e:
        print(f"Error downloading media from {url}: {e}")
        return None


def cleanup_file(file_path: Optional[str]):
    """Safely removes temporary media files from disk after processing/sending."""
    if file_path and os.path.exists(file_path):
        try:
            os.remove(file_path)
        except Exception as e:
            print(f"Error removing temp file {file_path}: {e}")