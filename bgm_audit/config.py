"""扫描参数与本地数据目录。"""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import asdict, dataclass, fields
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


@dataclass
class Settings:
    shazam_window: float = 12.0
    shazam_step: float = 6.0
    request_interval: float = 2.0
    request_timeout: float = 25.0
    retries: int = 2
    local_window: float = 30.0
    local_step: float = 15.0
    min_hashes: int = 15
    min_match_seconds: float = 1.0
    merge_gap: float = 1.5

    def validate(self) -> Settings:
        for window, step in (
            (self.shazam_window, self.shazam_step),
            (self.local_window, self.local_step),
        ):
            if not 1 <= step <= window <= 120:
                raise ValueError("切片参数须满足 1 ≤ 步长 ≤ 窗口 ≤ 120 秒")
        # 官方当前签名窗口支持至 12 秒；15 秒起无法有效识别。
        if self.shazam_window > 12:
            raise ValueError("Shazam 窗口请设置在 1–12 秒，推荐 12 秒")
        if not 0 <= self.retries <= 5 or not 0 <= self.request_interval <= 60:
            raise ValueError("重试次数须在 0–5，请求间隔须在 0–60 秒")
        if not 1 <= self.request_timeout <= 120:
            raise ValueError("超时须在 1–120 秒")
        if not 5 <= self.min_hashes <= 1000 or not 0.1 <= self.min_match_seconds <= 30:
            raise ValueError("本地匹配阈值无效")
        if not 0 <= self.merge_gap <= 10:
            raise ValueError("合并容差须在 0–10 秒")
        return self


class Paths:
    def __init__(self, root: str | os.PathLike[str] | None = None) -> None:
        # 空的 BGM_DATA_DIR 视为未设置，避免把数据写进当前工作目录。
        base = root or os.environ.get("BGM_DATA_DIR") or ROOT / "data"
        self.root = Path(base).expanduser().resolve()
        self.library = self.root / "library"
        self.videos = self.root / "videos"
        self.temp = self.root / "temp"
        self.previews = self.root / "previews"
        self.index = self.root / "fingerprints.pklz"
        self.db = self.root / "audit.sqlite3"
        self.lock = self.root / "library.lock"
        for directory in (self.root, self.library, self.videos, self.temp, self.previews):
            directory.mkdir(parents=True, exist_ok=True)

    def load_settings(self) -> Settings:
        """读取设置；文件损坏或取值无效时回退默认值，忽略旧版本遗留的未知字段。"""
        target = self.root / "settings.json"
        if not target.exists():
            return Settings()
        try:
            raw = json.loads(target.read_text(encoding="utf-8"))
            if not isinstance(raw, dict):
                return Settings()
            known = {f.name for f in fields(Settings)}
            return Settings(**{k: v for k, v in raw.items() if k in known}).validate()
        except (ValueError, TypeError):
            return Settings()

    def save_settings(self, settings: Settings) -> None:
        settings.validate()
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=self.root, delete=False, suffix=".json") as f:
            json.dump(asdict(settings), f, ensure_ascii=False, indent=2)
        os.replace(f.name, self.root / "settings.json")
