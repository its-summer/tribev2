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
import os

from ..tts.edge import BYTES_PER_SAMPLE, CHANNELS, SAMPLE_RATE, silence

logger = logging.getLogger(__name__)

# 每次写入的音频块时长 (秒); 小块写入便于按实时速率喂数据
CHUNK_SECONDS = 0.2
CHUNK_BYTES = int(SAMPLE_RATE * CHUNK_SECONDS) * CHANNELS * BYTES_PER_SAMPLE

# 重启策略
MAX_FAST_FAILURES = 8      # 连续"启动即崩"次数上限, 超过判定为配置错误
STABLE_RUN_SECONDS = 30    # 进程存活超过此值视为一次稳定运行, 重置失败计数
MAX_BACKOFF_SECONDS = 30

# 帧驱动模式: 单路写缓冲上限 (约 12 帧 720p BGR), 超过则软背压等待 ffmpeg 消化
MAX_WRITE_BUFFER = 32 * 1024 * 1024


class RtmpStreamer:
    def __init__(
        self,
        avatar_video: str,
        output_url: str,
        container: str = "flv",
        auto_restart: bool = True,
        duration: float | None = None,
        performer=None,
    ):
        self.avatar_video = avatar_video
        self.output_url = output_url
        self.container = container       # flv (rtmp) | mp4 (本地文件)
        self.auto_restart = auto_restart
        self.duration = duration         # 限时录制 (dry-run); None=不限时
        # performer 存在 = 帧驱动口型同步模式 (画面逐帧由模型生成); 否则形象视频循环
        self.performer = performer
        self._proc: asyncio.subprocess.Process | None = None
        self._audio_queue: asyncio.Queue[bytes] = asyncio.Queue()
        self._supervisor: asyncio.Task | None = None
        self._stopping = False
        self._live = False

    async def start(self) -> None:
        self._stopping = False
        if self.performer:
            await self.performer.start()
        self._supervisor = asyncio.create_task(self._supervise())
        # 等监督器把第一路 ffmpeg 拉起来
        while not self._live and not self._stopping:
            await asyncio.sleep(0.05)

    _ENCODE = [
        "-c:v", "libx264", "-preset", "veryfast", "-tune", "zerolatency",
        "-pix_fmt", "yuv420p", "-g", "60", "-b:v", "2500k",
        "-c:a", "aac", "-b:a", "128k", "-ar", "44100",
    ]

    def _ffmpeg_args(self) -> list[str]:
        """循环模式: 形象视频无限循环 (画面) + stdin 读 PCM (声音)."""
        args = [
            "ffmpeg", "-hide_banner", "-loglevel", "warning", "-y",
            "-re", "-stream_loop", "-1", "-i", self.avatar_video,
            "-f", "s16le", "-ar", str(SAMPLE_RATE), "-ac", str(CHANNELS), "-i", "pipe:0",
            "-map", "0:v", "-map", "1:a", *self._ENCODE,
        ]
        if self.duration is not None:
            args += ["-t", str(self.duration)]
        args += ["-f", self.container, self.output_url]
        return args

    def _ffmpeg_args_frames(self, video_fd: int, audio_fd: int) -> list[str]:
        """帧驱动模式: rawvideo (口型帧) + s16le (语音) 两路管道输入."""
        from ..creation.lipsync import FPS, FRAME_HEIGHT, FRAME_WIDTH

        args = [
            "ffmpeg", "-hide_banner", "-loglevel", "warning", "-y",
            "-f", "rawvideo", "-pix_fmt", "bgr24",
            "-s", f"{FRAME_WIDTH}x{FRAME_HEIGHT}", "-r", str(FPS), "-i", f"pipe:{video_fd}",
            "-f", "s16le", "-ar", str(SAMPLE_RATE), "-ac", str(CHANNELS), "-i", f"pipe:{audio_fd}",
            "-map", "0:v", "-map", "1:a", *self._ENCODE,
        ]
        # 帧模式不用 ffmpeg -t: 限时由喂帧数控制, 喂够后关闭管道 (EOF) 让 ffmpeg
        # 自行收尾 —— 避免 ffmpeg 到 -t 停止读取而阻塞写线程造成死锁。
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
        if self.performer:
            await self._run_once_frames()
        else:
            await self._run_once_loop()

    async def _run_once_loop(self) -> None:
        """循环模式: 启动一路 ffmpeg, 持续喂音频直到其退出."""
        proc = await asyncio.create_subprocess_exec(
            *self._ffmpeg_args(), stdin=asyncio.subprocess.PIPE
        )
        self._proc = proc
        try:
            await self._pace_audio(proc)
        finally:
            await proc.wait()

    async def _run_once_frames(self) -> None:
        """帧驱动模式: 两路管道 (视频+音频), 锁步逐帧喂入直到 ffmpeg 退出."""
        loop = asyncio.get_running_loop()
        v_r, v_w = os.pipe()
        a_r, a_w = os.pipe()
        os.set_inheritable(v_r, True)
        os.set_inheritable(a_r, True)
        proc = await asyncio.create_subprocess_exec(
            *self._ffmpeg_args_frames(v_r, a_r), pass_fds=(v_r, a_r)
        )
        os.close(v_r)
        os.close(a_r)
        # 同帧的画面与音频"同时"递交给写缓冲, ffmpeg 才能立即交织两路、不卡读;
        # 不调 drain (大帧 drain 会死锁), 改用软背压控制内存。
        vt = await _pipe_writer(loop, v_w)
        at = await _pipe_writer(loop, a_w)
        self._proc = proc
        try:
            await self._pump_frames(proc, vt, at)
        finally:
            for t in (vt, at):
                if not t.is_closing():
                    t.close()
            await proc.wait()

    async def _pump_frames(self, proc, vt, at) -> None:
        """每 1/fps 秒锁步写一帧画面 + 该帧对齐音频, 保证音画同步.

        限时 (dry-run) 喂满 duration*fps 帧即返回, finally 关闭管道触发 ffmpeg 收尾;
        直播 (duration=None) 持续喂帧, 直到 stop() 或 ffmpeg 退出 (transport 关闭)。
        """
        fps = self.performer.fps
        dt = 1 / fps
        budget = int(self.duration * fps) if self.duration is not None else None
        loop = asyncio.get_running_loop()
        next_deadline = loop.time()
        written = 0
        while proc.returncode is None and not self._stopping and not vt.is_closing():
            if budget is not None and written >= budget:
                break
            frame, audio = await self.performer.tick()
            # 同帧画面+音频同时入写缓冲, 让 ffmpeg 立即交织两路 (不调 drain: 大帧会死锁)。
            # 实时节奏下 ffmpeg(veryfast) 可实时消化, 写缓冲自然有界; 若编码长期跟不上
            # 是算力问题, 需在部署侧 (降码率/GPU 编码) 解决, 不在此处阻塞喂帧。
            vt.write(frame)
            at.write(audio)
            written += 1
            # 写缓冲持续偏高说明 ffmpeg 编码跟不上实时 (算力不足); 每 ~5s 提醒一次
            if vt.get_write_buffer_size() > MAX_WRITE_BUFFER and written % (fps * 5) == 0:
                logger.warning("帧写缓冲偏高 (%d MB), ffmpeg 编码可能跟不上实时, 建议降码率或用 GPU 编码",
                               vt.get_write_buffer_size() // (1024 * 1024))
            next_deadline += dt
            delay = next_deadline - loop.time()
            if delay > 0:
                await asyncio.sleep(delay)
            else:
                next_deadline = loop.time()

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

    def enqueue_speech(self, pcm: bytes, gap_seconds: float = 0.8) -> None:
        """加入一段口播语音。帧驱动模式交给 performer 渲染口型; 循环模式入音频队列。"""
        if self.performer:
            self.performer.enqueue_speech(pcm)
        else:
            self.enqueue_pcm(pcm)
            self.enqueue_pcm(silence(gap_seconds))

    def enqueue_pcm(self, pcm: bytes) -> None:
        """(循环模式) 把一段语音 PCM 加入播出队列 (跨 ffmpeg 重启保留)."""
        for i in range(0, len(pcm), CHUNK_BYTES):
            self._audio_queue.put_nowait(pcm[i : i + CHUNK_BYTES])

    @property
    def pending_audio_seconds(self) -> float:
        """尚未播出的语音时长, 用于调度节奏 (两种模式统一接口)."""
        if self.performer:
            return self.performer.pending_seconds
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
        if self.performer:
            await self.performer.stop()
        self._proc = None
        self._live = False

    @property
    def alive(self) -> bool:
        """是否仍在 (或正尝试) 直播。重启退避期间仍为 True, 以便上游继续生成内容。"""
        return self._live


async def _pipe_writer(loop, fd: int):
    """把 OS 管道写端包装成 asyncio 写 transport (write/close/缓冲查询, 不用 drain)."""
    transport, _ = await loop.connect_write_pipe(
        asyncio.streams.FlowControlMixin, os.fdopen(fd, "wb")
    )
    return transport
