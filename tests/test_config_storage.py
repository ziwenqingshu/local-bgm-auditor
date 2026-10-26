import json
import sqlite3
from dataclasses import asdict

import pytest

from bgm_audit.config import Paths, Settings
from bgm_audit.reports import export_csv, safe_cell
from bgm_audit.storage import Store, like_pattern

# ---------------------------------------------------------------- 设置


@pytest.mark.parametrize(
    "change",
    [
        {"local_window": 10, "local_step": 20},
        {"local_window": 121, "local_step": 15},
        {"shazam_window": 15, "shazam_step": 6},
        {"retries": 6},
        {"request_interval": 61},
        {"request_timeout": 0.5},
        {"min_hashes": 4},
        {"min_match_seconds": 0},
        {"merge_gap": 11},
    ],
)
def test_invalid_settings_rejected(change):
    with pytest.raises(ValueError):
        Settings(**change).validate()


def test_default_settings_valid():
    assert Settings().validate() == Settings()


def test_settings_roundtrip_and_fallbacks(tmp_path):
    paths = Paths(tmp_path / "d")
    assert paths.load_settings() == Settings()
    custom = Settings(local_window=20, local_step=10)
    paths.save_settings(custom)
    assert paths.load_settings() == custom
    assert not list(paths.root.glob("tmp*.json"))
    with pytest.raises(ValueError):
        paths.save_settings(Settings(local_step=99, local_window=10))
    assert paths.load_settings() == custom  # 无效设置不会覆盖已保存的设置

    target = paths.root / "settings.json"
    target.write_text("{not json", encoding="utf-8")
    assert paths.load_settings() == Settings()
    target.write_text("[1, 2]", encoding="utf-8")
    assert paths.load_settings() == Settings()
    target.write_text(json.dumps({"local_window": "abc"}), encoding="utf-8")
    assert paths.load_settings() == Settings()


def test_unknown_keys_from_other_versions_do_not_reset_settings(tmp_path):
    paths = Paths(tmp_path / "d")
    data = dict(asdict(Settings(merge_gap=3)), removed_option=True)
    (paths.root / "settings.json").write_text(json.dumps(data), encoding="utf-8")
    assert paths.load_settings().merge_gap == 3


def test_data_dir_env_and_empty_env(tmp_path, monkeypatch):
    monkeypatch.setenv("BGM_DATA_DIR", str(tmp_path / "env_data"))
    assert Paths().root == (tmp_path / "env_data").resolve()
    for sub in ("library", "videos", "temp", "previews"):
        assert (tmp_path / "env_data" / sub).is_dir()
    monkeypatch.setenv("BGM_DATA_DIR", "")
    monkeypatch.setattr("bgm_audit.config.ROOT", tmp_path / "project")
    monkeypatch.chdir(tmp_path)
    # 空变量回退到项目内 data/，而不是把数据写进当前工作目录。
    assert Paths().root == (tmp_path / "project" / "data").resolve()


# ---------------------------------------------------------------- 存储


def make_task(store, filename, note=""):
    task_id = store.create_task(filename, "unused.mp4", ["audfprint"], "用途", {})
    store.finish_task(task_id, 1, [], [], "未检出，仍需复核")
    if note:
        store.review(task_id, note, "未处理")
    return task_id


def test_search_treats_like_wildcards_literally(tmp_path):
    store = Store(Paths(tmp_path / "d"))
    plain = make_task(store, "第1集.mp4")
    underscore = make_task(store, "ep_2.mp4")
    percent = make_task(store, "100%完成.mp4")
    assert {t["id"] for t in store.tasks("_")} == {underscore}
    assert {t["id"] for t in store.tasks("%")} == {percent}
    assert {t["id"] for t in store.tasks("")} == {plain, underscore, percent}
    assert {t["id"] for t in store.tasks("第1")} == {plain}
    assert like_pattern("a\\b") == "%a\\\\b%"


def test_search_covers_notes(tmp_path):
    store = Store(Paths(tmp_path / "d"))
    task = make_task(store, "a.mp4", note="已联系版权方")
    make_task(store, "b.mp4")
    assert [t["id"] for t in store.tasks("版权方")] == [task]


def test_review_log_keeps_snapshots_and_missing_task_errors(tmp_path):
    store = Store(Paths(tmp_path / "d"))
    task_id = make_task(store, "a.mp4")
    store.review(task_id, "一", "未处理")
    store.review(task_id, "二", "已人工复核")
    task = store.get_task(task_id)
    assert [r["note"] for r in task["reviews"]] == ["一", "二"]
    assert task["note"] == "二" and task["reviews"][0]["snapshot"]["status"] == "未检出，仍需复核"
    with pytest.raises(ValueError, match="任务不存在"):
        store.review("missing", "x", "y")
    assert store.get_task("missing") is None
    store.delete_task("missing")  # 不存在时静默


def test_delete_task_keeps_files_outside_data_dir(tmp_path):
    paths = Paths(tmp_path / "d")
    store = Store(paths)
    outside = tmp_path / "用户原片.mp4"
    outside.write_bytes(b"x")
    task_id = store.create_task("用户原片.mp4", outside, ["audfprint"], "用途", {})
    preview = paths.previews / f"{task_id}_0.mp4"
    preview.write_bytes(b"p")
    store.delete_task(task_id)
    assert outside.exists() and not preview.exists()


def test_remove_track_never_deletes_outside_library(tmp_path):
    paths = Paths(tmp_path / "d")
    store = Store(paths)
    outside = tmp_path / "原始.wav"
    outside.write_bytes(b"x")
    track = dict(id="t", title="t", artist="", source="", path=outside, sha256="0", duration=1.0, license={})
    store.add_track(track, b"")
    before = store.revision()
    store.remove_track("t")
    assert outside.exists() and store.revision() == before + 1
    store.remove_track("t")  # 重复删除不报错


def test_old_database_without_snapshot_column_is_migrated(tmp_path):
    paths = Paths(tmp_path / "d")
    with sqlite3.connect(paths.db) as db:
        db.execute(
            "CREATE TABLE reviews (id INTEGER PRIMARY KEY, task_id TEXT NOT NULL, note TEXT NOT NULL, "
            "conclusion TEXT NOT NULL, created_at TEXT NOT NULL)"
        )
    store = Store(paths)
    task_id = make_task(store, "a.mp4", note="迁移后")
    assert store.get_task(task_id)["reviews"][0]["snapshot"]["status"]


# ---------------------------------------------------------------- 报告


@pytest.mark.parametrize("value", ["=1+1", "+1", "-1", "@SUM(A1)", "\t=1", "\r=1", "  =1"])
def test_formula_like_cells_are_neutralised(value):
    assert safe_cell(value).startswith("'")


@pytest.mark.parametrize(("value", "expected"), [(-1.5, "-1.5"), (3, "3"), ("曲名", "曲名"), ("", "")])
def test_numbers_and_plain_text_unchanged(value, expected):
    assert safe_cell(value) == expected


def test_csv_for_task_without_detections_has_one_row():
    task = dict(
        id="t", filename="a.mp4", created_at="2026", purpose="用途", status="未检出，仍需复核",
        state="completed", detections=[], errors=[], note="", conclusion="", reviews=[],
    )  # fmt: skip
    lines = export_csv([task]).decode("utf-8-sig").strip().splitlines()
    assert len(lines) == 2 and lines[1].startswith("t,a.mp4")
