import os
import asyncio
from typing import Optional


async def get_video_duration(input_path: str) -> Optional[float]:
    """Retrieves video duration in seconds using ffprobe."""
    cmd = [
        'ffprobe', '-v', 'error',
        '-show_entries', 'format=duration',
        '-of', 'default=noprint_wrappers=1:nokey=1',
        input_path
    ]
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, _ = await proc.communicate()
        return float(stdout.decode().strip())
    except Exception as e:
        print(f"Error reading video duration: {e}")
        return None


async def compress_video_to_size(
    input_path: str, 
    target_size_mb: float = 48.0
) -> Optional[str]:
    """
    Compresses a video file using FFmpeg to ensure its size stays below target_size_mb.
    Calculates target video bitrate automatically based on duration.
    """
    if not os.path.exists(input_path):
        return None

    file_size_mb = os.path.getsize(input_path) / (1024 * 1024)
    
    # If already smaller than target, return original path
    if file_size_mb <= target_size_mb:
        return input_path

    duration = await get_video_duration(input_path)
    if not duration or duration <= 0:
        return None

    # Calculate target bitrate (bits per second)
    # Total Target Bits = Target MB * 1024 * 1024 * 8
    target_bits = target_size_mb * 1024 * 1024 * 8
    total_bitrate = target_bits / duration
    
    # Reserve 128k for audio stream
    audio_bitrate = 128000
    video_bitrate = int(total_bitrate - audio_bitrate)

    if video_bitrate <= 100000:
        video_bitrate = 100000  # Minimum safe bitrate threshold

    output_path = os.path.splitext(input_path)[0] + "_compressed.mp4"

    # FFmpeg single-pass encode with hard size ceiling
    ffmpeg_cmd = [
        'ffmpeg', '-y',
        '-i', input_path,
        '-c:v', 'libx264',
        '-b:v', f'{video_bitrate}',
        '-maxrate', f'{int(video_bitrate * 1.2)}',
        '-bufsize', f'{int(video_bitrate * 2)}',
        '-preset', 'faster',
        '-c:a', 'aac',
        '-b:a', '128k',
        output_path
    ]

    try:
        proc = await asyncio.create_subprocess_exec(*ffmpeg_cmd)
        await proc.wait()

        if os.path.exists(output_path) and os.path.getsize(output_path) > 0:
            return output_path
    except Exception as e:
        print(f"Error compressing video with FFmpeg: {e}")

    return None