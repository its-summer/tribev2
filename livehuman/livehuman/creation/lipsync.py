"""口型同步接入层: 让数字人的口型跟随 TTS 语音.

最难、也最值钱的工程不是模型本身, 而是把"逐帧生成的画面"与"TTS 语音"严格
对齐后送进实时直播流。本模块负责模型无关的那一半:

- AvatarFrames     用 ffmpeg 把形象循环视频解码为定尺 BGR24 原始帧 (可测)
- Performance      一段话渲染出的 帧序列 + 对齐音频
- LipSyncDriver    口型驱动接口: render(语音PCM) -> Performance; 兼供空闲帧
- IdleLipSyncDriver  无模型回退: 口型不动但音画照常播出, 用于验证整条管线
- MuseTalkDriver   依赖注入推理函数的适配器 (需 GPU + 权重, 不臆造其 API)
- Performer        后台预渲染 + 实时锁步取帧, 把渲染时延与播出节奏解耦

帧尺寸/帧率固定 (口型模型通常要求定尺输入), 与 stream 层共用 FRAME_* 常量。
"""

from __future__ import annotations

import asyncio
import logging
import math
import subprocess
from dataclasses import dataclass, field
from typing import Callable, Protocol

from ..tts.edge import BYTES_PER_SAMPLE, CHANNELS, SAMPLE_RATE

logger = logging.getLogger(__name__)

# 帧规格 (竖屏 9:16); 口型模型与推流共用
FRAME_WIDTH = 720
FRAME_HEIGHT = 1280
FPS = 25
SAMPLES_PER_FRAME = SAMPLE_RATE // FPS
AUDIO_BYTES_PER_FRAME = SAMPLES_PER_FRAME * CHANNELS * BYTES_PER_SAMPLE
FRAME_BYTES = FRAME_WIDTH * FRAME_HEIGHT * 3  # BGR24


def load_avatar_frames(
    video: str, width: int = FRAME_WIDTH, height: int = FRAME_HEIGHT, fps: int = FPS
) -> list[bytes]:
    """把形象视频解码并缩放为定尺 BGR24 原始帧列表 (空闲循环 + 口型模型参考帧)."""
    proc = subprocess.run(
        ["ffmpeg", "-hide_banner", "-loglevel", "error", "-i", video,
         "-s", f"{width}x{height}", "-r", str(fps), "-pix_fmt", "bgr24",
         "-f", "rawvideo", "pipe:1"],
        capture_output=True,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"解码形象视频失败: {proc.stderr.decode(errors='replace')[-400:]}")
    raw = proc.stdout
    n = width * height * 3
    frames = [raw[i : i + n] for i in range(0, len(raw) - n + 1, n)]
    if not frames:
        raise RuntimeError(f"形象视频未解出任何帧: {video}")
    return frames


@dataclass
class Performance:
    """一段语音渲染出的画面与对齐音频 (len(frames) 帧, audio 为对齐后的 PCM)."""

    frames: list[bytes]
    audio: bytes


class LipSyncDriver(Protocol):
    def render(self, speech_pcm: bytes) -> Performance:
        """把一段语音渲染成口型同步的帧序列 + 对齐音频."""
        ...

    def idle_frame(self, index: int) -> bytes:
        """空闲(无人说话)时的画面帧, index 单调递增以便循环播放."""
        ...


def _frames_for_audio(pcm: bytes) -> int:
    return max(1, math.ceil(len(pcm) / AUDIO_BYTES_PER_FRAME))


class IdleLipSyncDriver:
    """无模型回退: 不做口型推理, 整段用空闲帧填充。

    口型不会动, 但音画时长对齐、能正常播出 —— 用于在没有 GPU/权重时跑通并
    验证整条帧驱动管线。接入真实模型后用 MuseTalkDriver 替换即可。
    """

    def __init__(self, avatar_frames: list[bytes]):
        self.avatar_frames = avatar_frames
        self._render_cursor = 0

    def render(self, speech_pcm: bytes) -> Performance:
        n = _frames_for_audio(speech_pcm)
        frames = [self._next(self._render_cursor + i) for i in range(n)]
        self._render_cursor += n
        audio = speech_pcm.ljust(n * AUDIO_BYTES_PER_FRAME, b"\x00")
        return Performance(frames=frames, audio=audio)

    def idle_frame(self, index: int) -> bytes:
        return self._next(index)

    def _next(self, index: int) -> bytes:
        return self.avatar_frames[index % len(self.avatar_frames)]


# 推理函数签名: (参考帧序列, 语音PCM, width, height, fps) -> 口型帧序列
InferFn = Callable[[list[bytes], bytes, int, int, int], list[bytes]]


class MuseTalkDriver:
    """MuseTalk (或同类实时口型模型) 适配器.

    模型推理通过注入的 infer_fn 完成 —— 本类只负责把语音切成帧、调用推理、
    对齐音频, 不臆造任何具体模型的 Python API。infer_fn 由使用方实现, 封装
    一次 MuseTalk 前向: 输入参考帧 + 语音, 输出等长的口型帧 (BGR24, 定尺)。

    需 GPU + 模型权重。未注入 infer_fn 时 render 报错, 提示改用 IdleLipSyncDriver。
    """

    def __init__(
        self,
        avatar_frames: list[bytes],
        infer_fn: InferFn | None = None,
        width: int = FRAME_WIDTH,
        height: int = FRAME_HEIGHT,
        fps: int = FPS,
    ):
        self.avatar_frames = avatar_frames
        self.infer_fn = infer_fn
        self.width, self.height, self.fps = width, height, fps
        self._idle_cursor = 0

    def render(self, speech_pcm: bytes) -> Performance:
        if self.infer_fn is None:
            raise NotImplementedError(
                "MuseTalkDriver 未注入推理函数 (infer_fn)。请用 register_musetalk() "
                "注册封装好的 MuseTalk 推理, 或改用 IdleLipSyncDriver 先跑通管线。"
            )
        n = _frames_for_audio(speech_pcm)
        # 取一段参考帧喂模型 (循环取, 与帧数对齐)
        ref = [self.avatar_frames[(self._idle_cursor + i) % len(self.avatar_frames)]
               for i in range(n)]
        self._idle_cursor += n
        frames = self.infer_fn(ref, speech_pcm, self.width, self.height, self.fps)
        if len(frames) != n:  # 模型输出帧数对齐到音频时长
            frames = (frames + [frames[-1]] * n)[:n] if frames else ref
        audio = speech_pcm.ljust(n * AUDIO_BYTES_PER_FRAME, b"\x00")
        return Performance(frames=frames, audio=audio)

    def idle_frame(self, index: int) -> bytes:
        return self.avatar_frames[index % len(self.avatar_frames)]


# 全局注册点: 使用方在启动时把封装好的 MuseTalk 推理注册进来
_MUSETALK_INFER: InferFn | None = None


def register_musetalk(infer_fn: InferFn) -> None:
    global _MUSETALK_INFER
    _MUSETALK_INFER = infer_fn


def build_driver(lipsync: str, avatar_frames: list[bytes]) -> LipSyncDriver:
    """按 persona.lipsync 选择驱动; 模型未注册时安全回退到静帧并告警."""
    if lipsync == "musetalk":
        if _MUSETALK_INFER is None:
            logger.warning(
                "persona 要求 musetalk 口型同步, 但未注册推理函数 —— "
                "回退到静帧 (口型不动)。请在启动时调用 register_musetalk()。"
            )
            return IdleLipSyncDriver(avatar_frames)
        return MuseTalkDriver(avatar_frames, infer_fn=_MUSETALK_INFER)
    return IdleLipSyncDriver(avatar_frames)


class Performer:
    """后台预渲染语音段为 Performance, 实时锁步逐帧取出 (帧 + 该帧音频)。

    渲染 (可能很慢, GPU 推理) 与播出 (每帧 1/fps 秒, 必须准时) 解耦: 渲染在
    后台任务里进行, 播出端只从就绪队列取已渲染好的帧, 队列空则播空闲帧。
    """

    def __init__(self, driver: LipSyncDriver, fps: int = FPS):
        self.driver = driver
        self.fps = fps
        self._speech: asyncio.Queue[bytes] = asyncio.Queue()
        self._ready: asyncio.Queue[Performance] = asyncio.Queue(maxsize=8)
        self._cur: Performance | None = None
        self._frame_i = 0
        self._idle_i = 0
        self._render_task: asyncio.Task | None = None

    async def start(self) -> None:
        self._render_task = asyncio.create_task(self._render_loop())

    async def stop(self) -> None:
        if self._render_task:
            self._render_task.cancel()
            self._render_task = None

    def enqueue_speech(self, pcm: bytes) -> None:
        self._speech.put_nowait(pcm)

    @property
    def pending_seconds(self) -> float:
        """尚未播出的语音时长估计 (待渲染 + 已就绪), 供上游调度节奏."""
        ready_frames = sum(len(p.frames) for p in list(self._ready._queue))
        cur_left = (len(self._cur.frames) - self._frame_i) if self._cur else 0
        # 待渲染段无法精确知道时长, 每段粗略按 1 帧计 (保守, 仅作低水位触发)
        return (ready_frames + cur_left) / self.fps + self._speech.qsize()

    async def _render_loop(self) -> None:
        loop = asyncio.get_running_loop()
        while True:
            pcm = await self._speech.get()
            # 渲染放到线程, 避免阻塞事件循环 (GPU/CPU 重活)
            perf = await loop.run_in_executor(None, self.driver.render, pcm)
            await self._ready.put(perf)

    async def tick(self) -> tuple[bytes, bytes]:
        """取下一帧画面 + 该帧对齐音频; 无就绪内容时返回空闲帧 + 静音."""
        if self._cur and self._frame_i < len(self._cur.frames):
            return self._emit_current()
        self._cur = None
        try:
            self._cur = self._ready.get_nowait()
            self._frame_i = 0
            return self._emit_current()
        except asyncio.QueueEmpty:
            frame = self.driver.idle_frame(self._idle_i)
            self._idle_i += 1
            return frame, b"\x00" * AUDIO_BYTES_PER_FRAME

    def _emit_current(self) -> tuple[bytes, bytes]:
        assert self._cur
        i = self._frame_i
        frame = self._cur.frames[i]
        audio = self._cur.audio[i * AUDIO_BYTES_PER_FRAME : (i + 1) * AUDIO_BYTES_PER_FRAME]
        audio = audio.ljust(AUDIO_BYTES_PER_FRAME, b"\x00")
        self._frame_i += 1
        return frame, audio
