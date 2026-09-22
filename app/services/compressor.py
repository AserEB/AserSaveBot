import os
import asyncio
import json
import shutil

async def get_video_duration(input_path: str) -> float:
    """Extracts exact video duration in seconds using ffprobe."""
    if not shutil.which("ffprobe"):
        return 0.0

    cmd = [
        "ffprobe",
        "-v", "quiet",
        "-print_format", "json",
        "-show_format",
        input_path
    ]
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, _ = await proc.communicate()
        data = json.loads(stdout.decode('utf-8', errors='ignore'))
        return float(data.get('format', {}).get('duration', 0.0))
    except Exception as e:
        print(f"Error extracting duration via ffprobe: {e}")
        return 0.0


async def compress_video_to_size(input_path: str, target_size_mb: float = 40.0) -> str:
    """
    Compresses video strictly under target_size_mb (default 40MB).
    Returns output path on success, or None on failure.
    """
    if not os.path.exists(input_path):
        return None

    # Verify if FFmpeg binary is installed on the system
    if not shutil.which("ffmpeg"):
        print("FFmpeg executable not found in system PATH!")
        return None

    current_size_mb = os.path.getsize(input_path) / (1024 * 1024)
    if current_size_mb <= target_size_mb:
        return input_path

    duration = await get_video_duration(input_path)
    if duration <= 0:
        duration = 600.0  # Fallback duration (10 mins)

    # Calculate strict target bitrate (leaving 10% safety margin)
    total_target_bits = (target_size_mb * 0.90) * 8 * 1024 * 1024
    total_bitrate = int(total_target_bits / duration)

    audio_bitrate = 64 * 1024  # 64 kbps audio
    video_bitrate = max(100 * 1024, total_bitrate - audio_bitrate)

    video_kbps = int(video_bitrate / 1024)
    audio_kbps = int(audio_bitrate / 1024)

    base, _ = os.path.splitext(input_path)
    output_path = f"{base}_compressed.mp4"

    cmd = [
        "ffmpeg", "-y",
        "-i", input_path,
        "-c:v", "libx264",
        "-b:v", f"{video_kbps}k",
        "-maxrate", f"{int(video_kbps * 1.15)}k",
        "-bufsize", f"{int(video_kbps * 1.5)}k",
        "-preset", "ultrafast",
        "-pix_fmt", "yuv420p",
        "-vf", "scale='min(640,iw)':-2",
        "-c:a", "aac",
        "-b:a", f"{audio_kbps}k",
        "-ac", "2",
        "-ar", "44100",
        "-movflags", "+faststart",
        output_path
    ]

    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        _, stderr = await proc.communicate()

        if os.path.exists(output_path) and os.path.getsize(output_path) > 1000:
            final_mb = os.path.getsize(output_path) / (1024 * 1024)
            print(f"Compressed strictly to: {final_mb:.2f} MB")
            return output_path
        else:
            print(f"FFmpeg compression stderr: {stderr.decode('utf-8', errors='ignore')}")
            return None
    except Exception as e:
        print(f"Compression error: {e}")
        return None