"""FFmpeg 推流: 形象视频无限循环 + 实时写入的音频管道, 带崩溃自动重启.

画面: persona 的 idle 循环视频 (-stream_loop -1)。
声音: 从 stdin 持续读取 s16le PCM —— 说话时写 TTS 音频, 空闲时由 pacing
      写静音, 保证音轨连续不断流。

稳定性: 监督器 (_supervise) 监控 ffmpeg 进程。直播 (auto_restart=True) 时,
ffmpeg 意外退出会自动重启并带退避; 音频队列跨重启保留, 已生成的口播不丢。
连续快速失败多次 (疑似配置错误) 才放弃。

输出目标: rtmp:// 用 flv 推流; 本地文件用 mp4 (供 dry-run 录制验证)。

升级到实时口型同步 (MuseTalk 等) 时, 只需把视频输入从循环文件换成
lip-sync 模型输出的帧管道, 本类接口不变。
"""

from __future__ import annotations

import asyncio
import logging

from ..tts.edge import BYTES_PER_SAMPLE, CHANNELS, SAMPLE_RATE, silence

logger = logging.getLogger(__name__)

# 每次写入的音频块时长 (秒); 小块写入便于按实时速率喂数据
CHUNK_SECONDS = 0.2
CHUNK_BYTES = int(SAMPLE_RATE * CHUNK_SECONDS) * CHANNELS * BYTES_PER_SAMPLE

# 重启策略
MAX_FAST_FAILURES = 8      # 连续"启动即崩"次数上限, 超过判定为配置错误
STABLE_RUN_SECONDS = 30    # 进程存活超过此值视为一次稳定运行, 重置失败计数
MAX_BACKOFF_SECONDS = 30


class RtmpStreamer:
    def __init__(
        self,
        avatar_video: str,
        output_url: str,
        container: str = "flv",
        auto_restart: bool = True,
        duration: float | None = None,
    ):
        self.avatar_video = avatar_video
        self.output_url = output_url
        self.container = container       # flv (rtmp) | mp4 (本地文件)
        self.auto_restart = auto_restart
        self.duration = duration         # 限时录制 (dry-run); None=不限时
        self._proc: asyncio.subprocess.Process | None = None
        self._audio_queue: asyncio.Queue[bytes] = asyncio.Queue()
        self._supervisor: asyncio.Task | None = None
        self._stopping = False
        self._live = False

    async def start(self) -> None:
        self._stopping = False
        self._supervisor = asyncio.create_task(self._supervise())
        # 等监督器把第一路 ffmpeg 拉起来
        while not self._live and not self._stopping:
            await asyncio.sleep(0.05)

    def _ffmpeg_args(self) -> list[str]:
        args = [
            "ffmpeg", "-hide_banner", "-loglevel", "warning",
            "-re", "-stream_loop", "-1", "-i", self.avatar_video,
            "-f", "s16le", "-ar", str(SAMPLE_RATE), "-ac", str(CHANNELS), "-i", "pipe:0",
            "-map", "0:v", "-map", "1:a",
            "-c:v", "libx264", "-preset", "veryfast", "-tune", "zerolatency",
            "-pix_fmt", "yuv420p", "-g", "60", "-b:v", "2500k",
            "-c:a", "aac", "-b:a", "128k", "-ar", "44100",
        ]
        if self.duration is not None:
            args += ["-t", str(self.duration)]
        args += ["-f", self.container, self.output_url]
        return args

    async def _supervise(self) -> None:
        """拉起 ffmpeg, 崩溃则按策略重启 (直播); dry-run 跑完一次即止."""
        self._live = True
        fast_failures = 0
        loop = asyncio.get_running_loop()
        try:
            while not self._stopping:
                started = loop.time()
                try:
                    await self._run_once()
                except asyncio.CancelledError:
                    raise
                except Exception:
                    logger.exception("ffmpeg 运行异常")
                if self._stopping or not self.auto_restart:
                    break

                ran = loop.time() - started
                fast_failures = 0 if ran >= STABLE_RUN_SECONDS else fast_failures + 1
                if fast_failures >= MAX_FAST_FAILURES:
                    logger.error(
                        "推流连续 %d 次启动即失败, 放弃重启 —— "
                        "请检查 RTMP 地址/推流密钥/网络/形象视频。",
                        fast_failures,
                    )
                    break
                backoff = 1.0 if ran >= STABLE_RUN_SECONDS else min(
                    2 ** fast_failures, MAX_BACKOFF_SECONDS
                )
                logger.warning("ffmpeg 已退出, %.1fs 后自动重启推流...", backoff)
                await asyncio.sleep(backoff)
        finally:
            self._live = False

    async def _run_once(self) -> None:
        """启动一路 ffmpeg, 持续喂音频直到其退出."""
        proc = await asyncio.create_subprocess_exec(
            *self._ffmpeg_args(), stdin=asyncio.subprocess.PIPE
        )
        self._proc = proc
        try:
            await self._pace_audio(proc)
        finally:
            await proc.wait()

    async def _pace_audio(self, proc: asyncio.subprocess.Process) -> None:
        """按实时速率向 ffmpeg 写音频; 队列空时写静音保持音轨连续."""
        assert proc.stdin
        stdin = proc.stdin
        silence_chunk = silence(CHUNK_SECONDS)
        loop = asyncio.get_running_loop()
        next_deadline = loop.time()
        while proc.returncode is None and not self._stopping:
            try:
                chunk = self._audio_queue.get_nowait()
            except asyncio.QueueEmpty:
                chunk = silence_chunk
            try:
                stdin.write(chunk)
                await stdin.drain()
            except (ConnectionResetError, BrokenPipeError):
                break  # ffmpeg 已退出, 交由 _run_once 收尾后重启
            next_deadline += CHUNK_SECONDS
            delay = next_deadline - loop.time()
            if delay > 0:
                await asyncio.sleep(delay)
            else:
                next_deadline = loop.time()

    def enqueue_pcm(self, pcm: bytes) -> None:
        """把一段语音 PCM 加入播出队列 (跨 ffmpeg 重启保留)."""
        for i in range(0, len(pcm), CHUNK_BYTES):
            self._audio_queue.put_nowait(pcm[i : i + CHUNK_BYTES])

    @property
    def pending_audio_seconds(self) -> float:
        """队列中尚未播出的音频时长, 用于调度节奏."""
        return self._audio_queue.qsize() * CHUNK_SECONDS

    async def stop(self) -> None:
        self._stopping = True
        if self._proc and self._proc.stdin:
            try:
                self._proc.stdin.close()
            except (ConnectionResetError, BrokenPipeError):
                pass
        if self._proc:
            try:
                await asyncio.wait_for(self._proc.wait(), timeout=5)
            except asyncio.TimeoutError:
                self._proc.kill()
        if self._supervisor:
            try:
                await asyncio.wait_for(self._supervisor, timeout=5)
            except (asyncio.TimeoutError, asyncio.CancelledError):
                self._supervisor.cancel()
        self._proc = None
        self._live = False

    @property
    def alive(self) -> bool:
        """是否仍在 (或正尝试) 直播。重启退避期间仍为 True, 以便上游继续生成内容。"""
        return self._live
