import os
import glob
import asyncio
import urllib.request
import traceback
import re
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
                headers={
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36',
                    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8'
                }
            )
            with urllib.request.urlopen(req, timeout=10) as response:
                resolved = response.geturl()
                if resolved.rstrip('/') != "https://www.pinterest.com":
                    target_url = resolved
        except Exception as e:
            print(f"Error resolving Pinterest url: {e}")

    if "tiktok.com" in target_url:
        target_url = target_url.split("?")[0]

    return target_url


def get_ydl_options_for_url(url: str) -> dict:
    """Provides optimized yt-dlp configurations with complete stream format parsing."""
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
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        }
    }

    if any(domain in url for domain in ["youtube.com", "youtu.be"]):
        # web and mweb guarantee standard video formats (1080p, 720p, 480p, 360p, 240p, 144p)
        options['extractor_args'] = {
            'youtube': {
                'player_client': ['web', 'mweb', 'android']
            }
        }

        # Check for cookies file
        local_cookie = os.path.join(BASE_DIR, "cookies.txt")
        env_cookie = os.getenv('YOUTUBE_COOKIES_TXT')

        if env_cookie and len(env_cookie.strip()) > 20:
            cookie_path = '/tmp/youtube_cookies.txt'
            try:
                content = env_cookie.strip()
                if not content.startswith('# Netscape'):
                    content = '# Netscape HTTP Cookie File\n' + content
                with open(cookie_path, 'w', encoding='utf-8') as f:
                    f.write(content)
                options['cookiefile'] = cookie_path
            except Exception as e:
                print(f"Error writing cookies from env: {e}")
        elif os.path.exists(local_cookie) and os.path.getsize(local_cookie) > 0:
            options['cookiefile'] = local_cookie

    elif "tiktok.com" in url:
        options['extractor_args'] = {
            'tiktok': {
                'api_hostname': 'api22-normal-c-useast2a.tiktokv.com'
            }
        }

    return options


async def extract_media_info(url: str) -> Optional[Dict[str, Any]]:
    """Extracts metadata safely without format restrictions."""
    real_url = resolve_url(url)
    ydl_opts = get_ydl_options_for_url(real_url)
    ydl_opts['skip_download'] = True

    def _extract():
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(real_url, download=False, process=False)
            if not info:
                return None
            return {
                "id": info.get("id"),
                "title": info.get("title", "Video"),
                "duration": info.get("duration", 0),
                "thumbnail": info.get("thumbnail") or (info.get("thumbnails")[-1]["url"] if info.get("thumbnails") else None),
                "channel": info.get("uploader", "Creator")
            }

    try:
        return await asyncio.to_thread(_extract)
    except Exception as e:
        print(f"Direct info extract failed: {e}. Trying standard fallback...")
        try:
            fallback_opts = get_ydl_options_for_url(real_url)
            fallback_opts['skip_download'] = True
            fallback_opts['extract_flat'] = True
            with yt_dlp.YoutubeDL(fallback_opts) as ydl:
                return await asyncio.to_thread(ydl.extract_info, real_url, download=False)
        except Exception as fe:
            print(f"Fallback extraction failed: {fe}")
            return None


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
            results.append({
                "id": entry.get("id"),
                "title": entry.get("title", "YouTube Video"),
                "url": video_url,
                "duration": entry.get("duration", 0),
                "thumbnails": entry.get("thumbnails", []),
                "thumbnail": entry.get("thumbnails")[-1]["url"] if entry.get("thumbnails") else None,
                "channel": entry.get("uploader", "YouTube Creator")
            })
        return results
    except Exception as e:
        print(f"YouTube search error for query '{query}': {e}")
        return []


async def download_media_file(
    url: str, 
    format_spec: str, 
    custom_filename: str
) -> Optional[str]:
    """Downloads media file with robust resolution sorting and universal fallbacks."""
    real_url = resolve_url(url)
    base_name = os.path.splitext(custom_filename)[0]
    outtmpl_pattern = os.path.join(DOWNLOAD_DIR, f"{base_name}.%(ext)s")
    
    ydl_opts = get_ydl_options_for_url(real_url)
    ydl_opts['outtmpl'] = outtmpl_pattern
    ydl_opts['overwrites'] = True

    is_audio = "mp3" in format_spec.lower() or "mp3" in custom_filename.lower()

    if is_audio:
        ydl_opts['format'] = 'ba/b'
        ydl_opts['postprocessors'] = [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': '192',
        }]
    else:
        # Determine exact height constraint
        target_height = "360"
        for h in ["1080", "720", "480", "360", "240", "144"]:
            if h in format_spec:
                target_height = h
                break
        
        # Priority: best matching height -> combined format -> any available stream
        ydl_opts['format'] = f"bestvideo[height<={target_height}]+bestaudio/best[height<={target_height}]/best"
        ydl_opts['format_sort'] = [f"res:{target_height}", "ext:mp4:m4a"]

    def _download(opts):
        with yt_dlp.YoutubeDL(opts) as ydl:
            ydl.download([real_url])

    try:
        await asyncio.to_thread(_download, ydl_opts)
    except Exception as e:
        print(f"Primary format failed: {e}. Retrying with universal fallback...")
        fallback_opts = get_ydl_options_for_url(real_url)
        fallback_opts['outtmpl'] = outtmpl_pattern
        fallback_opts['overwrites'] = True
        
        if is_audio:
            fallback_opts['format'] = 'bestaudio/best'
            fallback_opts['postprocessors'] = [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '192',
            }]
        else:
            fallback_opts['format'] = 'best'
        
        try:
            await asyncio.to_thread(_download, fallback_opts)
        except Exception as fe:
            print(f"Fallback download completely failed: {fe}")
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