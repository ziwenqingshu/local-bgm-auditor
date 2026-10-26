from dataclasses import asdict
from pathlib import Path
from unittest.mock import AsyncMock
import csv
import io
import json

from bgm_audit.config import Settings
from bgm_audit.models import Detection
from bgm_audit.reports import export_csv, export_json
from bgm_audit.storage import Store
from test_shazam import FakeShazam


def test_history_persists_review_exports_and_deletion(env, media_files):
    paths, store, service = env
    fake = FakeShazam([{"track": {"key": "42", "title": "=曲名", "subtitle": "歌手"}}]*3)
    settings = Settings(request_interval=0, retries=0)
    task = service.audit(media_files["video"], ["shazam"], "漫剧商业发布", settings, shazam_factory=lambda: fake)
    assert task["state"] == "completed" and not task["errors"]
    assert len(task["detections"]) == 1
    assert len(task["detections"][0]["evidence"]) == 3
    store.review(task["id"], "待补授权材料", "待补充授权")
    fresh = Store(paths).get_task(task["id"])
    assert fresh["note"] == "待补授权材料"
    assert fresh["reviews"][0]["conclusion"] == "待补充授权"
    assert store.tasks("曲名")[0]["id"] == task["id"]
    csv_rows = list(csv.DictReader(io.StringIO(export_csv([fresh]).decode("utf-8-sig"))))
    assert csv_rows[0]["音乐"] == "'=曲名"
    assert json.loads(csv_rows[0]["原始切片证据JSON"])[1]["window_start"] == 6
    decoded = json.loads(export_json([fresh]))
    assert decoded["tasks"][0]["note"] == "待补授权材料"
    assert decoded["tasks"][0]["detections"][0]["start"] == 0
    retained = Path(fresh["video_path"])
    assert retained.is_file() and list(paths.temp.iterdir()) == []
    store.delete_task(task["id"])
    assert not retained.exists() and store.get_task(task["id"]) is None


def test_network_failure_saved_in_history(env, media_files):
    paths, store, service = env
    fake = FakeShazam([OSError("offline")]*3)
    task = service.audit(media_files["video"], ["shazam"], "用途", Settings(retries=0, request_interval=0),
                         shazam_factory=lambda: fake)
    assert task["status"] == "识别不完整"
    assert len(task["errors"]) == 3
    assert all(e["kind"] == "网络失败" for e in task["errors"])
    assert Store(paths).get_task(task["id"])["errors"] == task["errors"]
    assert not list(paths.temp.iterdir())


def test_no_audio_failure_is_retained_and_cleaned(env, media_files):
    paths, store, service = env
    task = service.audit(media_files["silent_video"], ["audfprint"], "用途", Settings())
    assert task["state"] == "failed" and task["status"] == "识别不完整"
    assert task["errors"][0]["kind"] == "无音轨"
    assert not list(paths.temp.iterdir())


def test_empty_library_is_not_reported_as_successful_scan(env, media_files):
    _, _, service = env
    task = service.audit(media_files["video"], ["audfprint"], "用途", Settings())
    assert task["status"] == "识别不完整" and task["errors"][0]["kind"] == "曲库为空"


def test_recheck_applies_current_license(real_library):
    paths, store, service, one, _ = real_library
    task_id = store.create_task("复查.mp4", "unused", ["audfprint"], "漫剧商业发布", asdict(Settings()))
    found = Detection("audfprint", one["id"], one["title"], one["artist"], 0, 10, "估计")
    store.finish_task(task_id, 10, [found.to_dict()], [], "待核验")
    checked = service.recheck(task_id)
    assert checked["status"] == "授权已核验"
    assert checked["detections"][0]["license_snapshot"]["verified"] is True
