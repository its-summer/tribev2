"""FFmpeg RTMP 推流: 形象视频无限循环 + 实时写入的音频管道.

画面: persona 的 idle 循环视频 (-stream_loop -1)。
声音: 从 stdin 持续读取 s16le PCM —— 说话时写 TTS 音频, 空闲时由
      pacing 协程写静音, 保证音轨连续不断流。

升级到实时口型同步 (MuseTalk 等) 时, 只需把视频输入从循环文件换成
lip-sync 模型输出的帧管道, 本类接口不变。
"""

from __future__ import annotations

import asyncio

from ..tts.edge import BYTES_PER_SAMPLE, CHANNELS, SAMPLE_RATE, silence

# 每次写入的音频块时长 (秒); 小块写入便于按实时速率喂数据
CHUNK_SECONDS = 0.2
CHUNK_BYTES = int(SAMPLE_RATE * CHUNK_SECONDS) * CHANNELS * BYTES_PER_SAMPLE


class RtmpStreamer:
    def __init__(self, avatar_video: str, rtmp_url: str):
        self.avatar_video = avatar_video
        self.rtmp_url = rtmp_url
        self._proc: asyncio.subprocess.Process | None = None
        self._audio_queue: asyncio.Queue[bytes] = asyncio.Queue()
        self._pacer_task: asyncio.Task | None = None

    async def start(self) -> None:
        self._proc = await asyncio.create_subprocess_exec(
            "ffmpeg",
            "-hide_banner", "-loglevel", "warning",
            # 视频: 形象循环
            "-re", "-stream_loop", "-1", "-i", self.avatar_video,
            # 音频: 从 stdin 读 PCM
            "-f", "s16le", "-ar", str(SAMPLE_RATE), "-ac", str(CHANNELS), "-i", "pipe:0",
            "-map", "0:v", "-map", "1:a",
            "-c:v", "libx264", "-preset", "veryfast", "-tune", "zerolatency",
            "-pix_fmt", "yuv420p", "-g", "60", "-b:v", "2500k",
            "-c:a", "aac", "-b:a", "128k", "-ar", "44100",
            "-f", "flv", self.rtmp_url,
            stdin=asyncio.subprocess.PIPE,
        )
        self._pacer_task = asyncio.create_task(self._pace_audio())

    def enqueue_pcm(self, pcm: bytes) -> None:
        """把一段语音 PCM 加入播出队列."""
        for i in range(0, len(pcm), CHUNK_BYTES):
            self._audio_queue.put_nowait(pcm[i : i + CHUNK_BYTES])

    @property
    def pending_audio_seconds(self) -> float:
        """队列中尚未播出的音频时长, 用于调度节奏."""
        return self._audio_queue.qsize() * CHUNK_SECONDS

    async def _pace_audio(self) -> None:
        """按实时速率向 ffmpeg 写音频; 队列空时写静音保持音轨连续."""
        assert self._proc and self._proc.stdin
        stdin = self._proc.stdin
        silence_chunk = silence(CHUNK_SECONDS)
        loop = asyncio.get_running_loop()
        next_deadline = loop.time()
        try:
            while True:
                try:
                    chunk = self._audio_queue.get_nowait()
                except asyncio.QueueEmpty:
                    chunk = silence_chunk
                stdin.write(chunk)
                await stdin.drain()
                # 音频本身按 -re 的视频节奏被 ffmpeg 消费, 这里按墙钟限速,
                # 避免一次性把队列灌进 ffmpeg 缓冲导致音画漂移
                next_deadline += CHUNK_SECONDS
                delay = next_deadline - loop.time()
                if delay > 0:
                    await asyncio.sleep(delay)
                else:
                    next_deadline = loop.time()
        except (ConnectionResetError, BrokenPipeError):
            pass  # ffmpeg 已退出, 由 stop()/wait 收尾

    async def stop(self) -> None:
        if self._pacer_task:
            self._pacer_task.cancel()
        if self._proc:
            if self._proc.stdin:
                self._proc.stdin.close()
            try:
                await asyncio.wait_for(self._proc.wait(), timeout=5)
            except asyncio.TimeoutError:
                self._proc.kill()
        self._proc = None

    @property
    def alive(self) -> bool:
        return self._proc is not None and self._proc.returncode is None
