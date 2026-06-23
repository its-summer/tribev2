"""从员工录制的产品讲解视频中提取数字人素材 (ffmpeg).

提取两类素材:
1. 语音样本 (wav): 用于声音克隆。1~3 分钟干净人声效果最佳。
2. 形象循环视频 (mp4): 截取一段表情动作自然的片段, 直播时无限循环。
   员工本人的真实画面天然保留了他的表情和动作; 实时口型同步
   (MuseTalk 等) 接入后, 将以这段视频为底驱动口型 —— 见 lipsync.py。
"""

from __future__ import annotations

import subprocess
from pathlib import Path


def _run(args: list[str]) -> None:
    proc = subprocess.run(args, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(f"ffmpeg 失败: {proc.stderr.strip()[-500:]}")


def extract_voice_sample(video: str | Path, out_wav: str | Path, max_seconds: int = 180) -> Path:
    """抽取音轨为单声道 wav, 作为声音克隆的训练样本."""
    out_wav = Path(out_wav)
    out_wav.parent.mkdir(parents=True, exist_ok=True)
    _run([
        "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
        "-i", str(video),
        "-t", str(max_seconds),
        "-vn", "-ac", "1", "-ar", "44100",
        str(out_wav),
    ])
    return out_wav


def extract_idle_loop(
    video: str | Path,
    out_mp4: str | Path,
    start: float = 0.0,
    duration: float = 20.0,
) -> Path:
    """截取一段无声形象视频作为直播画面循环.

    建议挑员工状态自然、动作幅度适中的片段 (start/duration 可调),
    首尾画面接近的片段循环起来更顺滑。
    """
    out_mp4 = Path(out_mp4)
    out_mp4.parent.mkdir(parents=True, exist_ok=True)
    _run([
        "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
        "-ss", str(start), "-t", str(duration),
        "-i", str(video),
        "-an",
        "-c:v", "libx264", "-preset", "medium", "-pix_fmt", "yuv420p",
        str(out_mp4),
    ])
    return out_mp4
