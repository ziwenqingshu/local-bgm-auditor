"""可选的 ShazamIO 联网识别。默认关闭，不属于离线流程。"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING, Any

from .media import slice_wav
from .models import Detection, EngineError

if TYPE_CHECKING:
    from .config import Settings


def client_factory(window: float = 12) -> Any:
    try:
        from aiohttp_retry import ExponentialRetry
        from shazamio import Shazam
        from shazamio.client import HTTPClient
    except ImportError as exc:
        raise RuntimeError("未安装可选 ShazamIO；运行安装脚本的 --with-shazam 模式") from exc
    # 禁用库内嵌重试，所有尝试次数由本应用的 retries 参数控制。
    return Shazam(
        segment_duration_seconds=round(window),
        http_client=HTTPClient(retry_options=ExponentialRetry(attempts=1)),
    )


class ProtocolError(RuntimeError):
    pass


def classify_error(exc: BaseException) -> tuple[str, str]:
    text = str(exc)
    if isinstance(exc, (asyncio.TimeoutError, TimeoutError)):
        return "超时", "Shazam 请求超时"
    if getattr(exc, "status", None) == 429 or "429" in text:
        return "服务限流", "Shazam 返回 429，服务限流，请稍后重试或增加请求间隔"
    if isinstance(exc, ProtocolError) or "ContentType" in type(exc).__name__:
        return "接口变更", "Shazam 响应结构异常，接口可能变更：" + text[:250]
    if isinstance(exc, OSError) or any(s in type(exc).__name__ for s in ("Connection", "Connector", "DNS")):
        return "网络失败", "无法连接 Shazam：" + text[:250]
    if "未安装" in text:
        return "依赖缺失", text
    return "服务异常", f"{type(exc).__name__}：{text[:250]}"


def parse_response(response: Any, start: float, end: float, index: int) -> Detection | None:
    if not isinstance(response, dict):
        raise ProtocolError("预期 JSON 对象")
    track = response.get("track")
    if not track:
        if isinstance(response.get("matches"), list) and not response["matches"]:
            return None
        raise ProtocolError("缺少 track 或有效的空 matches 列表")
    if not isinstance(track, dict) or not track.get("title"):
        raise ProtocolError("缺少歌曲名称")
    ids = {k: track[k] for k in ("key", "isrc", "url") if track.get(k)}
    hub = track.get("hub") or {}
    for option in hub.get("options", []):
        for action in option.get("actions", []):
            if action.get("type") == "applemusicplay" and action.get("id"):
                ids["apple_music_id"] = action["id"]
    title, artist = track["title"], track.get("subtitle", "")
    track_id = str(track.get("key") or track.get("isrc") or f"{title}|{artist}")
    return Detection(
        "shazam",
        track_id,
        title,
        artist,
        start,
        end,
        "识别切片覆盖区间（估计）",
        [dict(segment_index=index, window_start=start, window_end=end)],
        ids,
    )


class ShazamScanner:
    def __init__(self, settings: Settings, factory: Callable[[], Any] | None = None) -> None:
        self.settings = settings
        self.factory = factory or (lambda: client_factory(settings.shazam_window))
        self._last_request: float | None = None

    async def scan(
        self,
        audio: Path,
        ranges: list[tuple[float, float]],
        work: Path,
        progress: Callable[[int, int, str], Any] | None = None,
    ) -> tuple[list[Detection], list[EngineError]]:
        detections: list[Detection] = []
        errors: list[EngineError] = []
        try:
            async with self.factory() as shazam:
                for index, (start, end) in enumerate(ranges):
                    clip = work / "shazam.wav"
                    try:
                        slice_wav(audio, clip, start, end)
                        for attempt in range(self.settings.retries + 1):
                            if self._last_request is not None:
                                delay = self.settings.request_interval - (time.monotonic() - self._last_request)
                                if delay > 0:
                                    await asyncio.sleep(delay)
                            self._last_request = time.monotonic()
                            try:
                                async with asyncio.timeout(self.settings.request_timeout):
                                    response = await shazam.recognize(str(clip))
                                found = parse_response(response, start, end, index)
                                if found:
                                    detections.append(found)
                                break
                            except Exception as exc:
                                kind, message = classify_error(exc)
                                retryable = kind not in ("接口变更", "依赖缺失")
                                if attempt == self.settings.retries or not retryable:
                                    errors.append(EngineError("shazam", kind, message, start, end, attempt + 1))
                                    break
                                await asyncio.sleep(min(2**attempt, 8))
                    finally:
                        clip.unlink(missing_ok=True)
                    if progress:
                        progress(index + 1, len(ranges), f"Shazam：{start:.1f}–{end:.1f} 秒")
        except Exception as exc:
            kind, message = classify_error(exc)
            errors.append(EngineError("shazam", kind, message))
        return detections, errors
