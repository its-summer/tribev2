"""声音克隆: 用员工的语音样本注册克隆音色.

当前实现 ElevenLabs Instant Voice Clone (1~3 分钟样本即可)。
如需私有化部署, 可替换为 GPT-SoVITS / CosyVoice / F5-TTS 等开源方案,
只要返回一个可供 tts 层引用的 voice_id 即可。
"""

from __future__ import annotations

from pathlib import Path

import httpx

from ..tts.elevenlabs import API_BASE, api_key


def clone_voice(name: str, audio_path: str | Path, description: str = "") -> str:
    """上传语音样本创建克隆音色, 返回 voice_id."""
    audio_path = Path(audio_path)
    with audio_path.open("rb") as f:
        resp = httpx.post(
            f"{API_BASE}/voices/add",
            headers={"xi-api-key": api_key()},
            data={"name": name, "description": description or f"{name} 的克隆音色 (LiveHuman)"},
            files={"files": (audio_path.name, f, "audio/wav")},
            timeout=300,
        )
    resp.raise_for_status()
    return resp.json()["voice_id"]
