"""多语言 TTS: 基于 edge-tts (免费, 40+ 语言).

输出统一为 16-bit 单声道 PCM (SAMPLE_RATE), 直接喂给 RTMP 推流的音频管道。
后续可平替为 ElevenLabs / Azure / MiniMax 等克隆音色服务, 只要实现
synthesize(text, voice) -> bytes(PCM) 即可。
"""

from __future__ import annotations

import asyncio

import edge_tts

SAMPLE_RATE = 24000
CHANNELS = 1
BYTES_PER_SAMPLE = 2  # s16le


async def synthesize(text: str, voice: str) -> bytes:
    """合成语音, 返回 s16le 单声道 PCM 字节流."""
    communicate = edge_tts.Communicate(text, voice)
    mp3 = bytearray()
    async for chunk in communicate.stream():
        if chunk["type"] == "audio":
            mp3.extend(chunk["data"])
    return await _mp3_to_pcm(bytes(mp3))


async def _mp3_to_pcm(mp3_data: bytes) -> bytes:
    """用 ffmpeg 把 mp3 解码为目标采样率的原始 PCM."""
    proc = await asyncio.create_subprocess_exec(
        "ffmpeg",
        "-hide_banner", "-loglevel", "error",
        "-i", "pipe:0",
        "-f", "s16le",
        "-ar", str(SAMPLE_RATE),
        "-ac", str(CHANNELS),
        "pipe:1",
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    pcm, err = await proc.communicate(mp3_data)
    if proc.returncode != 0:
        raise RuntimeError(f"ffmpeg 解码 TTS 音频失败: {err.decode(errors='replace')}")
    return pcm


def silence(duration_seconds: float) -> bytes:
    """生成指定时长的静音 PCM."""
    n = int(SAMPLE_RATE * duration_seconds) * CHANNELS * BYTES_PER_SAMPLE
    return b"\x00" * n
