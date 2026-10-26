"""审核流水线：复制视频 → 提取音轨 → 分段识别 → 合并 → 授权规则 → 保存。"""

from __future__ import annotations

import asyncio
import shutil
import tempfile
import uuid
from collections.abc import Callable
from dataclasses import asdict
from pathlib import Path
from typing import TYPE_CHECKING, Any

from .fingerprint import FingerprintLibrary
from .media import MediaError, NoAudioError, extract_audio, probe, slice_wav, windows
from .models import Detection, EngineError
from .review import merge_detections, review_detections
from .shazam_engine import ShazamScanner

if TYPE_CHECKING:
    from .config import Paths, Settings
    from .storage import Store

Progress = Callable[[float, float, str], Any]


class AuditService:
    def __init__(self, paths: Paths, store: Store) -> None:
        self.paths, self.store = paths, store
        self.library = FingerprintLibrary(paths, store)

    def audit(
        self,
        path: str | Path,
        engines: list[str],
        purpose: str,
        settings: Settings,
        progress: Progress | None = None,
        shazam_factory: Callable[[], Any] | None = None,
    ) -> dict[str, Any]:
        settings.validate()
        # 授权用途按完全一致比较；首尾空白不应导致已核验授权失效。
        purpose = purpose.strip()
        if not engines or set(engines) - {"audfprint", "shazam"}:
            raise ValueError("请选择有效识别引擎")
        path = Path(path).resolve()
        if path.suffix.lower() not in (".mp4", ".mov"):
            raise ValueError("审核视频仅支持 MP4、MOV")
        if not purpose:
            raise ValueError("请填写当前用途")
        if not path.is_file():
            raise ValueError("视频文件不存在")
        # 保存独立的原视频副本，用于历史复查；大文件使用路径导入而非上传。
        retained = self.paths.videos / f"{uuid.uuid4().hex}{path.suffix.lower()}"
        shutil.copy2(path, retained)
        try:
            task_id = self.store.create_task(path.name, retained, engines, purpose, asdict(settings))
        except Exception:
            retained.unlink(missing_ok=True)
            raise
        duration = 0.0
        detections: list[Detection] = []
        errors: list[EngineError] = []
        state = "completed"
        try:
            info = probe(retained)
            duration = info.duration
            with tempfile.TemporaryDirectory(dir=self.paths.temp, prefix="audit_") as directory:
                work = Path(directory)
                if progress:
                    progress(0, 1, "正在提取音轨…")
                audio = extract_audio(retained, work / "audio.wav", info)
                jobs = []
                if "audfprint" in engines:
                    jobs.append(("audfprint", windows(duration, settings.local_window, settings.local_step)))
                if "shazam" in engines:
                    jobs.append(("shazam", windows(duration, settings.shazam_window, settings.shazam_step)))
                total = sum(len(r) for _, r in jobs)
                finished = 0
                for engine, ranges in jobs:
                    if engine == "audfprint":
                        if not self.store.tracks():
                            errors.append(EngineError(engine, "曲库为空", "本地曲库为空，请先导入参考音乐"))
                            finished += len(ranges)
                            continue
                        for index, (start, end) in enumerate(ranges):
                            clip = work / "local.wav"
                            try:
                                slice_wav(audio, clip, start, end)
                                detections += self.library.match(clip, start, end, settings, index)
                            except Exception as exc:
                                errors.append(EngineError(engine, "本地匹配失败", str(exc), start, end))
                            finally:
                                clip.unlink(missing_ok=True)
                            finished += 1
                            if progress:
                                progress(finished, total, f"本地指纹：{start:.1f}–{end:.1f} 秒")
                    else:

                        def on_progress(done: float, _: float, message: str, base: int = finished) -> None:
                            if progress:
                                progress(base + done, total, message)

                        found, failures = asyncio.run(
                            ShazamScanner(settings, shazam_factory).scan(audio, ranges, work, on_progress)
                        )
                        detections += found
                        errors += failures
                        finished += len(ranges)
                if progress:
                    progress(total, total, "识别完成，正在保存报告…")
        except NoAudioError as exc:
            errors.append(EngineError("ffmpeg", "无音轨", str(exc)))
            state = "failed"
        except Exception as exc:
            errors.append(EngineError("ffmpeg" if isinstance(exc, MediaError) else "pipeline", "处理失败", str(exc)))
            state = "failed"
        merged = merge_detections(detections, settings.merge_gap)
        reviewed, status = review_detections(merged, purpose, errors)
        self.store.finish_task(
            task_id, duration, [d.to_dict() for d in reviewed], [e.to_dict() for e in errors], status, state
        )
        return self._task(task_id)

    def recheck(self, task_id: str) -> dict[str, Any]:
        """按当前曲库授权材料重新核验，历史识别证据和人工复查日志保留。"""
        task = self.store.get_task(task_id)
        if task is None:
            raise ValueError("任务不存在")
        tracks = {t["id"]: t for t in self.store.tracks()}
        found = [Detection(**d) for d in task["detections"]]
        for d in found:
            if d.engine == "audfprint":
                track = tracks.get(d.track_id)
                d.license_snapshot = track["license"] if track else {}
                if track:
                    d.title, d.artist = track["title"], track["artist"]
        reviewed, status = review_detections(found, task["purpose"], task["errors"])
        # 先记录一条复查日志（含重核前的状态快照），再写入新结果。
        self.store.review(task_id, task["note"], task["conclusion"])
        self.store.finish_task(
            task_id, task["duration"], [d.to_dict() for d in reviewed], task["errors"], status, task["state"]
        )
        return self._task(task_id)

    def _task(self, task_id: str) -> dict[str, Any]:
        task = self.store.get_task(task_id)
        if task is None:  # pragma: no cover - 刚写入的任务不会消失
            raise ValueError("任务不存在")
        return task
