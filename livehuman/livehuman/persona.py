"""数字人 (Persona) 定义与加载.

每个数字人是一份 YAML 配置, 描述人设、直播主题、支持语言与语音方案,
以及一段循环播放的形象视频路径。

两类数字人:
- 虚拟数字人: 手写 YAML + edge-tts 公共音色 (voice_provider: edge)
- 员工克隆数字人: 由 creation 流水线从员工录制的产品讲解视频自动生成
  (voice_provider: elevenlabs, 用克隆音色多语言发声, 并携带授权记录)
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field


class SourceInfo(BaseModel):
    """员工克隆数字人的来源与授权记录 (合规必需)."""

    employee_name: str
    employee_id: str = ""
    native_language: str = Field(
        default="",
        description="员工的母语/录制语言。克隆音色会带其口音, 故应作为该数字人的主直播语言",
    )
    consent_doc: str = Field(description="员工书面授权文件路径")
    source_video: str = Field(description="原始录制视频路径")
    created_at: str = ""


class StreamConfig(BaseModel):
    """该数字人的推流目标与互动账号.

    每个市场的数字人推到各自的 TikTok 账号, 用各自的推流密钥, 故凭据归属到
    persona 而非全局。推流地址是"整体回退": persona 未配置 rtmp_url 时, 整个
    推流目标回退到环境变量 (而非逐字段合并), 避免出现缺密钥的半截地址。
    监听账号 tiktok_unique_id 单独回退。见 pipeline.resolve_*。

    安全提示: stream_key 是敏感凭据。若 persona YAML 会进版本库, 不要写死密钥
    —— 把密钥放进 rtmp_url 的环境变量, 或用密钥管理在运行时注入。
    """

    rtmp_url: str = Field(default="", description="TikTok LIVE 推流服务器地址")
    stream_key: str = Field(default="", description="推流密钥 (敏感, 建议用密钥管理注入)")
    tiktok_unique_id: str = Field(default="", description="评论监听的 TikTok 账号 @unique_id")

    def full_rtmp_url(self) -> str:
        """拼出完整推流地址; 未配置 rtmp_url 时返回空串 (交由上层回退)."""
        if not self.rtmp_url:
            return ""
        return f"{self.rtmp_url.rstrip('/')}/{self.stream_key}" if self.stream_key else self.rtmp_url


class Persona(BaseModel):
    name: str
    description: str = Field(description="人设描述, 会进入系统提示词")
    primary_language: str = Field(default="en", description="主语言, 如 en / zh / es")
    languages: list[str] = Field(default_factory=lambda: ["en"], description="支持的语言列表")
    voice_provider: Literal["edge", "elevenlabs"] = Field(
        default="edge", description="edge=公共音色按语言切换; elevenlabs=克隆音色多语言"
    )
    voices: dict[str, str] = Field(
        default_factory=dict,
        description="(edge) 语言 -> 音色名, 如 {'zh': 'zh-CN-XiaoxiaoNeural'}",
    )
    voice_clone_id: str | None = Field(
        default=None, description="(elevenlabs) 克隆音色的 voice_id"
    )
    topics: list[str] = Field(default_factory=list, description="直播话题池")
    avatar_video: str = Field(description="形象循环视频路径 (mp4)")
    style_notes: str = Field(default="", description="语言风格补充, 如口头禅、节奏")
    market: str = Field(default="", description="归属市场代码, 如 jp / us (见 markets.yaml)")
    stream: StreamConfig | None = Field(
        default=None, description="推流目标与监听账号; 缺省回退到环境变量"
    )
    source: SourceInfo | None = Field(default=None, description="员工克隆数字人的来源记录")

    def voice_for(self, language: str) -> str:
        """(edge) 取某语言的音色, 没配则回退到主语言音色."""
        if not self.voices:
            raise ValueError(f"数字人「{self.name}」未配置 edge-tts 音色 (voices)")
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
