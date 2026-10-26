"""CSV / JSON 报告导出。"""

from __future__ import annotations

import csv
import io
import json
from datetime import UTC, datetime
from typing import Any

DISCLAIMER = "识别与区间均有误差；结果仅辅助核对授权记录，不构成法律结论。未检出不代表没有受版权保护的音乐。"

# OWASP CSV 注入：这些前缀会被电子表格解释为公式或控制字符。
FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r")

CSV_FIELDS = [
    "任务ID", "视频", "审核时间UTC", "当前用途", "任务状态", "执行状态", "音乐", "歌手", "识别来源",
    "歌曲标识", "开始秒", "结束秒", "区间说明", "歌曲审核状态", "判断依据", "原始切片证据JSON",
    "授权快照JSON", "识别错误JSON", "人工备注", "人工结论", "复查日志JSON", "提示",
]  # fmt: skip


def export_json(tasks: list[dict[str, Any]]) -> bytes:
    report = dict(
        schema_version="1.0",
        exported_at=datetime.now(UTC).isoformat(),
        notice=DISCLAIMER,
        tasks=tasks,
    )
    return json.dumps(report, ensure_ascii=False, indent=2).encode("utf-8")


def safe_cell(value: Any) -> str:
    """防止用户曲名、备注在电子表格中被当作公式执行。"""
    if isinstance(value, int | float) and not isinstance(value, bool):
        return str(value)
    text = str(value)
    return "'" + text if text.lstrip(" ").startswith(FORMULA_PREFIXES) else text


def _encode(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False)


def export_csv(tasks: list[dict[str, Any]]) -> bytes:
    out = io.StringIO(newline="")
    writer = csv.writer(out)
    writer.writerow(CSV_FIELDS)
    for task in tasks:
        for d in task["detections"] or [{}]:
            row = [
                task["id"], task["filename"], task["created_at"], task["purpose"], task["status"],
                task["state"], d.get("title", ""), d.get("artist", ""), d.get("engine", ""),
                _encode(d.get("identifiers", {})), d.get("start", ""), d.get("end", ""),
                d.get("range_kind", ""), d.get("status", ""), d.get("reason", ""),
                _encode(d.get("evidence", [])), _encode(d.get("license_snapshot", {})),
                _encode(task["errors"]), task["note"], task["conclusion"], _encode(task["reviews"]),
                DISCLAIMER,
            ]  # fmt: skip
            writer.writerow([safe_cell(v) for v in row])
    return out.getvalue().encode("utf-8-sig")
