"""按 persona 的语音方案分发 TTS 请求."""

from __future__ import annotations

from ..persona import Persona
from . import edge, elevenlabs


async def synthesize(persona: Persona, text: str, language: str) -> bytes:
    """合成口播语音, 返回 s16le 24kHz 单声道 PCM."""
    if persona.voice_provider == "elevenlabs":
        if not persona.voice_clone_id:
            raise ValueError(f"数字人「{persona.name}」缺少 voice_clone_id")
        # 多语言模型自动按文本语言发声, 无需切换音色
        return await elevenlabs.synthesize(text, persona.voice_clone_id)
    return await edge.synthesize(text, persona.voice_for(language))
