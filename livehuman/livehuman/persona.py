"""数字人 (Persona) 定义与加载.

每个数字人是一份 YAML 配置, 描述人设、直播主题、支持语言与各语言的 TTS 音色,
以及一段循环播放的形象视频路径。
"""

from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import BaseModel, Field


class Persona(BaseModel):
    name: str
    description: str = Field(description="人设描述, 会进入系统提示词")
    primary_language: str = Field(default="en", description="主语言, 如 en / zh / es")
    languages: list[str] = Field(default_factory=lambda: ["en"], description="支持的语言列表")
    voices: dict[str, str] = Field(
        description="语言 -> edge-tts 音色名, 如 {'zh': 'zh-CN-XiaoxiaoNeural'}"
    )
    topics: list[str] = Field(default_factory=list, description="直播话题池")
    avatar_video: str = Field(description="形象循环视频路径 (mp4)")
    style_notes: str = Field(default="", description="语言风格补充, 如口头禅、节奏")

    def voice_for(self, language: str) -> str:
        """取某语言的音色, 没配则回退到主语言音色."""
        return self.voices.get(language) or self.voices[self.primary_language]


def load_persona(path: str | Path) -> Persona:
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    return Persona.model_validate(data)


def list_personas(directory: str | Path) -> dict[str, Persona]:
    """加载目录下全部 persona YAML, 以文件名(不含扩展名)为 key."""
    personas = {}
    for f in sorted(Path(directory).glob("*.yaml")):
        personas[f.stem] = load_persona(f)
    return personas
