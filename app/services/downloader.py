import os
import asyncio
import urllib.request
import traceback
import re
from typing import Dict, Any, Optional
import yt_dlp

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DOWNLOAD_DIR = os.path.join(BASE_DIR, "downloads")
os.makedirs(DOWNLOAD_DIR, exist_ok=True)


def resolve_url(url: str) -> str:
    """Follows redirects for short links (pin.it, vt.tiktok.com) and cleans tracking params."""
    target_url = url.strip()
    
    # 1. Handle Pinterest short links
    if "pin.it" in target_url:
        try:
            req = urllib.request.Request(
                target_url,
                headers={
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36',
                    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8'
                }
            )
            with urllib.request.urlopen(req, timeout=10) as response:
                resolved = response.geturl()
                # If redirected to generic landing, extract pin path if available
                if resolved.rstrip('/') != "https://www.pinterest.com":
                    target_url = resolved
        except Exception as e:
            print(f"Error resolving Pinterest url: {e}")

    # 2. Clean tracking query parameters for TikTok to prevent status code 0 error
    if "tiktok.com" in target_url:
        target_url = target_url.split("?")[0]

    return target_url


def get_ydl_options_for_url(url: str) -> dict:
    """Provides optimized yt-dlp configurations per platform."""
    # Base configuration
    options = {
        'quiet': False,
        'no_warnings': False,
        'noplaylist': True,
        'geo_bypass': True,
        'nocheckcertificate': True,
        'source_address': '0.0.0.0',
        'http_headers': {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36',
            'Accept-Language': 'en-US,en;q=0.9',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
        }
    }

    # YouTube Specific Options
    if any(domain in url for domain in ["youtube.com", "youtu.be"]):
        options['js_runtimes'] = {'node': {}}
        options['extractor_args'] = {
            'youtube': {
                'player_client': ['android_vr', 'tv_downgraded', 'mweb']
            }
        }
        options['http_headers']['User-Agent'] = 'Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Mobile Safari/537.36'
        
        cookie_content = os.getenv('YOUTUBE_COOKIES_TXT')
        if cookie_content:
            cookie_path = '/tmp/youtube_cookies.txt'
            try:
                if not cookie_content.startswith('# Netscape'):
                    cookie_content = '# Netscape HTTP Cookie File\n' + cookie_content
                with open(cookie_path, 'w', encoding='utf-8') as f:
                    f.write(cookie_content)
                options['cookiefile'] = cookie_path
            except Exception as e:
                print(f"Error writing cookies: {e}")

    # TikTok Specific Options
    elif "tiktok.com" in url:
        options['extractor_args'] = {
            'tiktok': {
                'api_hostname': 'api22-normal-c-useast2a.tiktokv.com'
            }
        }

    return options


async def extract_media_info(url: str) -> Optional[Dict[str, Any]]:
    """Extracts metadata without downloading."""
    real_url = resolve_url(url)
    ydl_opts = get_ydl_options_for_url(real_url)
    ydl_opts['skip_download'] = True

    def _extract():
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            return ydl.extract_info(real_url, download=False)

    try:
        return await asyncio.to_thread(_extract)
    except Exception as e:
        print(f"Error extracting metadata from {url}: {repr(e)}")
        traceback.print_exc()
        return None


async def download_media_file(
    url: str, 
    format_spec: str, 
    custom_filename: str
) -> Optional[str]:
    """Downloads media file using yt-dlp with automatic format fallbacks."""
    real_url = resolve_url(url)
    output_path = os.path.join(DOWNLOAD_DIR, custom_filename)
    ydl_opts = get_ydl_options_for_url(real_url)
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
            ydl.download([real_url])
        return output_path

    try:
        path = await asyncio.to_thread(_download, ydl_opts)
        if os.path.exists(path):
            return path
    except Exception as e:
        print(f"Primary format failed: {e}. Retrying with universal fallback...")
        fallback_opts = get_ydl_options_for_url(real_url)
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
        except Exception:
            pass