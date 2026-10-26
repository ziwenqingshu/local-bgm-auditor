from copy import deepcopy
import re


def merge_detections(detections, gap=1.5):
    """同引擎同歌曲、相邻扫描且时间相接才合并，保留全部切片证据。"""
    grouped = {}
    for detection in detections:
        grouped.setdefault((detection.engine, detection.track_id), []).append(deepcopy(detection))
    result = []
    for group in grouped.values():
        group.sort(key=lambda d: (d.start, d.end))
        current = None
        for found in group:
            if current is not None:
                left = max((e.get("segment_index", 0) for e in current.evidence), default=0)
                right = min((e.get("segment_index", 0) for e in found.evidence), default=0)
                adjacent = right <= left+1
            else:
                adjacent = False
            if current is not None and found.start <= current.end+gap and adjacent:
                current.end = max(current.end, found.end)
                current.evidence.extend(found.evidence)
            else:
                current = found
                result.append(current)
    return sorted(result, key=lambda d: (d.start, d.engine, d.title))


def authorization_status(license_info, purpose):
    if license_info.get("coverage") == "明确不覆盖":
        return "不通过", "登记的授权信息明确不覆盖当前使用"
    covered = purpose in license_info.get("purposes", [])
    if (license_info.get("status") == "已登记授权" and license_info.get("verified")
            and license_info.get("coverage") == "覆盖已选用途" and covered
            and str(license_info.get("evidence", "")).strip()):
        return "授权已核验", f"授权已人工核实且登记覆盖用途：{purpose}；仍需核对材料有效期和实际发布条件"
    return "待核验", "没有同时满足已核实、授权依据和当前用途覆盖的授权记录"


def identity(detection):
    clean = lambda value: re.sub(r"[\W_]", "", value.casefold())
    return clean(detection.title), clean(detection.artist)


def review_detections(detections, purpose, errors):
    result = deepcopy(detections)
    for detection in result:
        if detection.engine == "audfprint":
            detection.status, detection.reason = authorization_status(detection.license_snapshot, purpose)
        else:
            detection.status, detection.reason = "待核验", "在线识别没有证明当前用途的授权"
    for i, left in enumerate(result):
        for right in result[i+1:]:
            overlap = min(left.end, right.end) - max(left.start, right.start)
            if left.engine != right.engine and overlap > 0 and identity(left) != identity(right):
                left.status = right.status = "人工复审"
                left.reason = right.reason = "不同识别引擎在重叠区间返回不同歌曲；也可能为混音，请人工复审"
    statuses = {d.status for d in result}
    if "不通过" in statuses:
        overall = "不通过"
    elif "人工复审" in statuses:
        overall = "人工复审"
    elif errors:
        overall = "识别不完整"
    elif not result:
        overall = "未检出，仍需复核"
    elif statuses == {"授权已核验"}:
        overall = "授权已核验"
    else:
        overall = "待核验"
    return result, overall
