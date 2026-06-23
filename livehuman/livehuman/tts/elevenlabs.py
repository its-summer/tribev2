"""ElevenLabs 克隆音色 TTS.

eleven_multilingual_v2 模型让同一个克隆音色直接说几十种语言 ——
员工只需录一段中文讲解, 数字人就能用"他自己的声音"说英语、西语、日语。

输出 pcm_24000 (s16le 24kHz 单声道), 与 tts/edge.py 的 SAMPLE_RATE 一致,
可直接进推流音频管道。
"""

from __future__ import annotations

import os

import httpx

API_BASE = "https://api.elevenlabs.io/v1"
MODEL_ID = "eleven_multilingual_v2"


def api_key() -> str:
    key = os.environ.get("ELEVENLABS_API_KEY", "")
    if not key:
        raise RuntimeError("请设置 ELEVENLABS_API_KEY")
    return key


async def synthesize(text: str, voice_id: str) -> bytes:
    """用克隆音色合成语音, 返回 s16le 24kHz 单声道 PCM."""
    async with httpx.AsyncClient(timeout=120) as client:
        resp = await client.post(
            f"{API_BASE}/text-to-speech/{voice_id}",
            params={"output_format": "pcm_24000"},
            headers={"xi-api-key": api_key()},
            json={"text": text, "model_id": MODEL_ID},
        )
        resp.raise_for_status()
        return resp.content
