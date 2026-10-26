from datetime import datetime, timezone
import csv
import io
import json

DISCLAIMER = "识别与区间均有误差；结果仅辅助核对授权记录，不构成法律结论。未检出不代表没有受版权保护的音乐。"


def export_json(tasks):
    report = dict(schema_version="1.0", exported_at=datetime.now(timezone.utc).isoformat(),
                  notice=DISCLAIMER, tasks=tasks)
    return json.dumps(report, ensure_ascii=False, indent=2).encode("utf-8")


def safe_cell(value):
    value = str(value)
    # 防止用户曲名、备注在电子表格中被当作公式执行。
    return "'"+value if value.lstrip().startswith(("=", "+", "-", "@")) else value


def export_csv(tasks):
    out = io.StringIO(newline="")
    fields = ["任务ID", "视频", "审核时间UTC", "当前用途", "任务状态", "执行状态", "音乐", "歌手", "识别来源",
              "歌曲标识", "开始秒", "结束秒", "区间说明", "歌曲审核状态", "判断依据", "原始切片证据JSON",
              "授权快照JSON", "识别错误JSON", "人工备注", "人工结论", "复查日志JSON", "提示"]
    writer = csv.writer(out)
    writer.writerow(fields)
    for task in tasks:
        for d in task["detections"] or [{}]:
            encode = lambda value: json.dumps(value, ensure_ascii=False)
            row = [task["id"], task["filename"], task["created_at"], task["purpose"], task["status"],
                   task["state"], d.get("title", ""), d.get("artist", ""), d.get("engine", ""),
                   encode(d.get("identifiers", {})), d.get("start", ""), d.get("end", ""),
                   d.get("range_kind", ""), d.get("status", ""), d.get("reason", ""),
                   encode(d.get("evidence", [])), encode(d.get("license_snapshot", {})),
                   encode(task["errors"]), task["note"], task["conclusion"], encode(task["reviews"]), DISCLAIMER]
            writer.writerow([safe_cell(v) for v in row])
    return out.getvalue().encode("utf-8-sig")
