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
        'format': 'b/bv*+ba/best',
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
    """Downloads media file using yt-dlp with automatic format fallbacks."""
    output_path = os.path.join(DOWNLOAD_DIR, custom_filename)
    
    ydl_opts = get_base_ydl_options()
    ydl_opts['outtmpl'] = output_path
    ydl_opts['overwrites'] = True

    # 1. Configure MP3 audio extraction if requested
    if "mp3" in format_spec.lower() or "mp3" in custom_filename.lower():
        ydl_opts['format'] = 'ba/bestaudio/b'
        ydl_opts['postprocessors'] = [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': '192',
        }]
    else:
        # 2. Flexible resolution formatting using wildcards
        if "1080" in format_spec:
            ydl_opts['format'] = 'bv*[height<=1080]+ba/b[height<=1080]/bv*+ba/b'
        elif "720" in format_spec:
            ydl_opts['format'] = 'bv*[height<=720]+ba/b[height<=720]/bv*+ba/b'
        elif "480" in format_spec:
            ydl_opts['format'] = 'bv*[height<=480]+ba/b[height<=480]/bv*+ba/b'
        else:
            ydl_opts['format'] = 'bv*+ba/b/best'

    def _download(options):
        with yt_dlp.YoutubeDL(options) as ydl:
            ydl.download([url])
        return output_path

    # Try downloading with primary format selection
    try:
        path = await asyncio.to_thread(_download, ydl_opts)
    except Exception as e:
        print(f"Primary format failed for {url}: {e}. Retrying with universal fallback 'b/best'...")
        
        # Fallback attempt if requested quality stream is missing or restricted
        fallback_opts = get_base_ydl_options()
        fallback_opts['outtmpl'] = output_path
        fallback_opts['overwrites'] = True
        fallback_opts['format'] = 'b/best'
        
        if "mp3" in custom_filename.lower():
            fallback_opts['postprocessors'] = [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '192',
            }]
            
        try:
            path = await asyncio.to_thread(_download, fallback_opts)
        except Exception as fallback_err:
            print(f"Fallback download also failed: {fallback_err}")
            return None

    # Check file status and handles extension changes by FFmpeg
    if path and os.path.exists(path):
        return path
    
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