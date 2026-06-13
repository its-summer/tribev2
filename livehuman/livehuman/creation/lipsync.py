"""实时口型同步接口 (预留): 让员工数字人的口型跟随 TTS 语音.

MVP 阶段直播画面是员工形象视频循环, 表情和动作来自真实录像但口型
不随语音变化。接入口型同步后, 数字人观感将接近员工本人在说话。

候选方案:
- MuseTalk   开源, 30fps+ 实时, 以 idle 视频为底驱动口型 —— 推荐起步
- Ditto      开源, 实时 talking-head
- HeyGen / D-ID  商业 API, 效果稳定但按分钟计费且延迟较高

接入方式: 实现 LipSyncDriver, 在 RtmpStreamer 中把视频输入从
"-stream_loop -1 -i idle.mp4" 换成 driver 输出的帧管道 (rawvideo pipe),
音频路径不变。
"""

from __future__ import annotations

from typing import AsyncIterator, Protocol


class LipSyncDriver(Protocol):
    """以形象视频为底、按音频驱动口型, 产出视频帧流."""

    async def start(self, idle_video: str) -> None:
        """加载底版视频与模型."""
        ...

    async def feed_audio(self, pcm: bytes) -> None:
        """送入将要播出的语音 PCM (s16le 24kHz 单声道)."""
        ...

    def frames(self) -> AsyncIterator[bytes]:
        """产出 BGR24 原始帧, 供 ffmpeg rawvideo 输入."""
        ...
