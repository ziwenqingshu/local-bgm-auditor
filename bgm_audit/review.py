"""区间合并与授权状态规则。规则表见 README「审核规则」。"""

from __future__ import annotations

import re
from collections.abc import Iterable, Sequence
from copy import deepcopy
from typing import Any

from .models import Detection

# 自动状态
PENDING = "待核验"
VERIFIED = "授权已核验"
REJECTED = "不通过"
MANUAL = "人工复审"
INCOMPLETE = "识别不完整"
NOT_FOUND = "未检出，仍需复核"
CONFLICT_REASON = "不同识别引擎在重叠区间返回不同歌曲；也可能为混音，请人工复审"


def merge_detections(detections: Iterable[Detection], gap: float = 1.5) -> list[Detection]:
    """同引擎同歌曲、相邻扫描且时间相接才合并，保留全部切片证据。"""
    grouped: dict[tuple[str, str], list[Detection]] = {}
    for detection in detections:
        grouped.setdefault((detection.engine, detection.track_id), []).append(deepcopy(detection))
    result: list[Detection] = []
    for group in grouped.values():
        group.sort(key=lambda d: (d.start, d.end))
        current: Detection | None = None
        for found in group:
            if current is not None:
                left = max((e.get("segment_index", 0) for e in current.evidence), default=0)
                right = min((e.get("segment_index", 0) for e in found.evidence), default=0)
                if right <= left + 1 and found.start <= current.end + gap:
                    current.end = max(current.end, found.end)
                    current.evidence.extend(found.evidence)
                    continue
            current = found
            result.append(current)
    return sorted(result, key=lambda d: (d.start, d.engine, d.title))


def _purposes(license_info: dict[str, Any]) -> set[str]:
    return {str(p).strip() for p in license_info.get("purposes", []) if str(p).strip()}


def authorization_status(license_info: dict[str, Any], purpose: str) -> tuple[str, str]:
    purpose = purpose.strip()
    if license_info.get("coverage") == "明确不覆盖":
        return REJECTED, "登记的授权信息明确不覆盖当前使用"
    if (
        license_info.get("status") == "已登记授权"
        and license_info.get("verified") is True
        and license_info.get("coverage") == "覆盖已选用途"
        and purpose in _purposes(license_info)
        and str(license_info.get("evidence", "")).strip()
    ):
        return VERIFIED, f"授权已人工核实且登记覆盖用途：{purpose}；仍需核对材料有效期和实际发布条件"
    return PENDING, "没有同时满足已核实、授权依据和当前用途覆盖的授权记录"


def identity(detection: Detection) -> tuple[str, str]:
    def clean(value: str) -> str:
        return re.sub(r"[\W_]", "", value.casefold())

    return clean(detection.title), clean(detection.artist)


def overall_status(statuses: set[str], has_errors: bool, has_detections: bool) -> str:
    """任务汇总：不通过 > 人工复审 > 识别不完整 > 未检出 > 全部已核验 > 待核验。"""
    if REJECTED in statuses:
        return REJECTED
    if MANUAL in statuses:
        return MANUAL
    if has_errors:
        return INCOMPLETE
    if not has_detections:
        return NOT_FOUND
    if statuses == {VERIFIED}:
        return VERIFIED
    return PENDING


def review_detections(
    detections: Sequence[Detection], purpose: str, errors: Sequence[Any]
) -> tuple[list[Detection], str]:
    result = deepcopy(list(detections))
    for detection in result:
        if detection.engine == "audfprint":
            detection.status, detection.reason = authorization_status(detection.license_snapshot, purpose)
        else:
            detection.status, detection.reason = PENDING, "在线识别没有证明当前用途的授权"
    for i, left in enumerate(result):
        for right in result[i + 1 :]:
            overlap = min(left.end, right.end) - max(left.start, right.start)
            if left.engine != right.engine and overlap > 0 and identity(left) != identity(right):
                for detection in (left, right):
                    # 已明确不通过的命中不能被冲突降级为人工复审，否则会掩盖拒绝结论。
                    if detection.status != REJECTED:
                        detection.status = MANUAL
                        detection.reason = CONFLICT_REASON
    statuses = {d.status for d in result}
    return result, overall_status(statuses, bool(errors), bool(result))
