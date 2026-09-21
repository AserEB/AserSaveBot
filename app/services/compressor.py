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
        val = stdout.decode().strip()
        return float(val) if val else None
    except Exception as e:
        print(f"Error reading video duration: {e}")
        return None


async def compress_video_to_size(
    input_path: str, 
    target_size_mb: float = 44.0
) -> Optional[str]:
    """
    Compresses video strictly under target_size_mb (default 44MB safe margin for Telegram 50MB limit).
    """
    if not os.path.exists(input_path):
        return None

    duration = await get_video_duration(input_path)
    if not duration or duration <= 0:
        return None

    # Target Bits: 44MB with safe margin for container overhead
    target_total_bits = target_size_mb * 1024 * 1024 * 8
    total_bitrate = target_total_bits / duration

    # 96k audio bitrate saves bandwidth for video
    audio_bitrate = 96000
    video_bitrate = int(total_bitrate - audio_bitrate)

    if video_bitrate <= 80000:
        video_bitrate = 80000

    output_path = os.path.splitext(input_path)[0] + "_comp.mp4"

    ffmpeg_cmd = [
        'ffmpeg', '-y',
        '-i', input_path,
        '-c:v', 'libx264',
        '-b:v', f'{video_bitrate}',
        '-maxrate', f'{int(video_bitrate * 1.1)}',
        '-bufsize', f'{int(video_bitrate * 1.5)}',
        '-preset', 'veryfast',
        '-vf', 'scale=-2:min(720\\,ih)',  # 1080p ከሆነ ወደ 720p ዝቅ በማድረግ ፋይሉ እንዳያብጥ ያደርጋል
        '-c:a', 'aac',
        '-b:a', '96k',
        output_path
    ]

    try:
        proc = await asyncio.create_subprocess_exec(*ffmpeg_cmd)
        await proc.wait()

        if os.path.exists(output_path) and os.path.getsize(output_path) > 0:
            final_size = os.path.getsize(output_path) / (1024 * 1024)
            print(f"Compressed file created successfully: {final_size:.2f} MB")
            return output_path
    except Exception as e:
        print(f"Error compressing video with FFmpeg: {e}")

    return None

compress_video = compress_video_to_size