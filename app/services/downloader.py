import os
import asyncio
from typing import Dict, Any, Optional
import yt_dlp

# Directory for storing temporary video/audio files
DOWNLOAD_DIR = "downloads"
os.makedirs(DOWNLOAD_DIR, exist_ok=True)


async def extract_media_info(url: str) -> Optional[Dict[str, Any]]:
    """
    Extracts video metadata (title, duration, qualities, thumbnail)
    without downloading the file. Runs in a background thread to prevent blocking.
    """
    ydl_opts = {
        'quiet': True,
        'no_warnings': True,
        'skip_download': True,
        'extract_flat': False,
    }

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
    """
    Downloads media file using yt-dlp based on requested format (1080p, 720p, MP3, etc).
    Returns path to downloaded file.
    """
    output_path = os.path.join(DOWNLOAD_DIR, custom_filename)
    
    ydl_opts = {
        'format': format_spec,
        'outtmpl': output_path,
        'quiet': True,
        'no_warnings': True,
        'overwrites': True,
    }

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
        
        # Check if extension changed (e.g., .mp3)
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