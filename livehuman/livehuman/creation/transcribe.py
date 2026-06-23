"""讲解视频转写: 拿到员工产品讲解的文字稿, 供风格分析使用.

优先使用本地 faster-whisper; 未安装时可在 builder 中用 --transcript
直接提供现成文字稿。
"""

from __future__ import annotations

from pathlib import Path


def transcribe(audio_path: str | Path) -> str:
    try:
        from faster_whisper import WhisperModel
    except ImportError as e:
        raise RuntimeError(
            "未安装 faster-whisper。请 `pip install faster-whisper`, "
            "或在命令行用 --transcript 提供讲解文字稿。"
        ) from e

    model = WhisperModel("small", compute_type="auto")
    segments, _info = model.transcribe(str(audio_path))
    return "".join(seg.text for seg in segments).strip()
