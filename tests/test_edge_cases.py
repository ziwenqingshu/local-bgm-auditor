"""边界情况：损坏文件、无音轨、多音轨、音轨偏移、重叠歌曲、空曲库及各类输入校验。"""

import subprocess
import wave
from pathlib import Path

import numpy as np
import pytest
from conftest import music, write_wav

from bgm_audit import media
from bgm_audit.config import Settings
from bgm_audit.media import (
    MediaError,
    _number,
    extract_audio,
    preview_clip,
    probe,
    run_ffmpeg,
    slice_wav,
    timecode,
    windows,
)

RATE = 16000


def offsets(task, track_id):
    return [e["reference_offset_seconds"] for d in task["detections"] if d["track_id"] == track_id
            for e in d["evidence"]]  # fmt: skip


# ---------------------------------------------------------------- 媒体层


@pytest.mark.parametrize("content", [b"", b"\x00not a real video" * 64])
def test_corrupt_or_empty_file_is_reported(tmp_path, content):
    broken = tmp_path / "损坏.mp4"
    broken.write_bytes(content)
    with pytest.raises(MediaError, match="无法读取媒体信息"):
        probe(broken)


def test_truncated_video_fails_cleanly(env, media_files, tmp_path):
    paths, _, service = env
    truncated = tmp_path / "截断.mp4"
    truncated.write_bytes(media_files["video"].read_bytes()[:2048])
    task = service.audit(truncated, ["audfprint"], "用途", Settings())
    assert task["state"] == "failed" and task["status"] == "识别不完整"
    assert task["errors"][0]["engine"] == "ffmpeg"
    assert list(paths.temp.iterdir()) == []


def test_corrupt_video_audit_is_failed_not_unmatched(env, tmp_path):
    paths, store, service = env
    broken = tmp_path / "损坏.mov"
    broken.write_bytes(b"garbage" * 100)
    task = service.audit(broken, ["audfprint"], "用途", Settings())
    assert task["state"] == "failed" and task["status"] == "识别不完整"
    assert task["errors"][0]["kind"] == "处理失败"
    assert store.tasks()[0]["id"] == task["id"]


def test_missing_file_and_bad_slice():
    with pytest.raises(MediaError, match="文件不存在"):
        probe("/definitely/not/here.mp4")
    with pytest.raises(MediaError, match="切片"):
        slice_wav("unused.wav", "out.wav", 5, 5)
    with pytest.raises(MediaError, match="切片"):
        slice_wav("unused.wav", "out.wav", -1, 5)


def test_slice_past_end_is_clamped(media_files, tmp_path):
    clip = slice_wav(media_files["refs"][0], tmp_path / "tail.wav", 20, 40)
    with wave.open(str(clip)) as reader:
        assert reader.getnframes() == 4 * RATE


def test_ffmpeg_failure_timeout_and_missing_binary(tmp_path, monkeypatch):
    with pytest.raises(MediaError, match="FFmpeg 处理失败"):
        run_ffmpeg(["-i", tmp_path / "missing.wav", tmp_path / "out.wav"])

    def slow(*args, **kwargs):
        raise subprocess.TimeoutExpired("ffmpeg", 1)

    monkeypatch.setattr(media.subprocess, "run", slow)
    with pytest.raises(MediaError, match="超时"):
        run_ffmpeg(["-version"])
    monkeypatch.setattr(media.shutil, "which", lambda name: None)
    with pytest.raises(MediaError, match="缺少 ffmpeg、ffprobe"):
        media.check_ffmpeg()


def test_probe_reads_audio_only_reference(media_files):
    info = probe(media_files["refs"][0])
    assert info.audio_offset == 0 and info.sample_rate == RATE and info.channels == 1
    assert 23.9 < info.duration < 24.1


def test_number_parser_handles_ffprobe_placeholders():
    assert _number("12.5") == 12.5
    assert _number("N/A", 3) == 3
    assert _number(None) == 0
    assert _number("nan", 1) == 1


def test_windows_with_fractional_step_end_exactly_at_duration():
    result = windows(10, 3, 2.5)
    assert result[0] == (0, 3) and result[-1][1] == 10
    assert all(b - a <= 3 for a, b in result)
    with pytest.raises(ValueError):
        windows(0, 3, 1)


def test_timecode_formatting():
    assert timecode(0) == "00:00:00.000"
    assert timecode(3723.4567) == "01:02:03.457"
    assert timecode(-5) == "00:00:00.000"


def test_preview_clip_is_playable_mp4(media_files, tmp_path):
    clip = preview_clip(media_files["video"], tmp_path / "preview.mp4", 2, 5)
    info = probe(clip)
    assert 2.5 < info.duration < 3.6


def test_multitrack_video_audits_only_first_audio_track(real_library, media_files, tmp_path):
    _, _, service, one, two = real_library
    video = tmp_path / "双音轨.mov"
    run_ffmpeg(["-f", "lavfi", "-i", "color=s=160x90:r=10:d=24", "-i", media_files["refs"][0],
                "-i", media_files["refs"][1], "-map", "0:v", "-map", "1:a", "-map", "2:a",
                "-c:v", "libx264", "-preset", "ultrafast", "-c:a", "aac", "-shortest", video])  # fmt: skip
    task = service.audit(video, ["audfprint"], "漫剧商业发布", Settings())
    ids = {d["track_id"] for d in task["detections"]}
    assert one["id"] in ids and two["id"] not in ids


def test_audio_starting_after_video_keeps_video_timeline(real_library, media_files, tmp_path):
    _, _, service, one, _ = real_library
    video = tmp_path / "音轨晚开始.mp4"
    run_ffmpeg(["-f", "lavfi", "-i", "color=s=160x90:r=10:d=16", "-itsoffset", 3,
                "-i", media_files["refs"][0], "-t", 16, "-c:v", "libx264", "-preset", "ultrafast",
                "-c:a", "aac", video])  # fmt: skip
    assert 2.8 < probe(video).audio_offset < 3.2
    task = service.audit(video, ["audfprint"], "漫剧商业发布", Settings())
    hit = next(d for d in task["detections"] if d["track_id"] == one["id"])
    assert hit["start"] >= 2.8  # 音轨开始前不可能有命中；支持区间可能晚于实际入点
    # 参考曲 0 秒对应视频 3 秒：参考时间 - 视频时间 ≈ -3。
    assert all(abs(o + 3) < 0.3 for o in offsets(task, one["id"]))


def test_audio_starting_before_video_is_trimmed_to_video_origin(real_library, media_files, tmp_path):
    _, _, service, one, _ = real_library
    video = tmp_path / "音轨早开始.mp4"
    run_ffmpeg(["-itsoffset", 2, "-f", "lavfi", "-i", "color=s=160x90:r=10:d=14",
                "-i", media_files["refs"][0], "-t", 16, "-c:v", "libx264", "-preset", "ultrafast",
                "-c:a", "aac", video])  # fmt: skip
    info = probe(video)
    assert -2.2 < info.audio_offset < -1.8
    wav = extract_audio(video, tmp_path / "trimmed.wav", info)
    with wave.open(str(wav)) as reader:
        assert abs(reader.getnframes() / RATE - info.duration) < 0.05
    task = service.audit(video, ["audfprint"], "漫剧商业发布", Settings())
    # 视频 0 秒对应参考曲 2 秒：参考时间 - 视频时间 ≈ +2。
    found = offsets(task, one["id"])
    assert found and all(abs(o - 2) < 0.3 for o in found)


def test_overlapping_songs_in_one_window_are_both_found(real_library, media_files, tmp_path):
    _, _, service, one, two = real_library
    both = media_files["first"][: 12 * RATE] * 0.7 + media_files["second"][: 12 * RATE] * 0.7
    mixed = write_wav(tmp_path / "叠加.wav", both)
    found = service.library.match(mixed, 0, 12, Settings())
    assert {one["id"], two["id"]} <= {d.track_id for d in found}


def test_song_boundaries_within_one_large_window(real_library, media_files):
    _, _, service, one, two = real_library
    found = service.library.match(media_files["audio"], 0, 24, Settings())
    first = next(d for d in found if d.track_id == one["id"])
    second = next(d for d in found if d.track_id == two["id"])
    assert 1.5 < first.start < first.end < 12.5
    assert 11.5 < second.start < second.end < 22.5


# ---------------------------------------------------------------- 曲库与流水线校验


def test_empty_library_match_returns_nothing(env, media_files):
    _, _, service = env
    assert service.library.match(media_files["audio"], 0, 24, Settings()) == []


def test_audit_input_validation(env, media_files, tmp_path):
    _, store, service = env
    with pytest.raises(ValueError, match="引擎"):
        service.audit(media_files["video"], [], "用途", Settings())
    with pytest.raises(ValueError, match="引擎"):
        service.audit(media_files["video"], ["acrcloud"], "用途", Settings())
    with pytest.raises(ValueError, match="MP4、MOV"):
        service.audit(tmp_path / "a.avi", ["audfprint"], "用途", Settings())
    with pytest.raises(ValueError, match="用途"):
        service.audit(media_files["video"], ["audfprint"], "   ", Settings())
    with pytest.raises(ValueError, match="不存在"):
        service.audit(tmp_path / "missing.mp4", ["audfprint"], "用途", Settings())
    with pytest.raises(ValueError):
        service.audit(media_files["video"], ["audfprint"], "用途", Settings(local_step=50))
    assert store.tasks() == []  # 校验失败不留下历史任务


def test_purpose_whitespace_does_not_break_verified_license(real_library, media_files):
    _, _, service, one, _ = real_library
    task = service.audit(media_files["video"], ["audfprint"], "  漫剧商业发布 ", Settings())
    assert task["purpose"] == "漫剧商业发布"
    assert next(d for d in task["detections"] if d["track_id"] == one["id"])["status"] == "授权已核验"


def test_recheck_after_track_deleted_and_license_changed(env, media_files):
    _, store, service = env
    licensed = dict(status="已登记授权", verified=True, coverage="覆盖已选用途",
                    purposes=["发布"], evidence="合同")  # fmt: skip
    one = service.library.import_file(media_files["refs"][0], "星河", license_info=licensed)
    service.library.import_file(media_files["refs"][1], "远山")
    task = service.audit(media_files["video"], ["audfprint"], "发布", Settings())
    assert task["status"] == "待核验"  # 远山没有授权

    two = next(t for t in store.tracks() if t["id"] != one["id"])
    store.update_track(two["id"], "远山（改名）", "乙", "来源", dict(licensed, coverage="明确不覆盖"))
    checked = service.recheck(task["id"])
    assert checked["status"] == "不通过"
    assert any(d["title"] == "远山（改名）" for d in checked["detections"])
    assert len(checked["reviews"]) == 1  # 重核前状态写入复查日志

    service.library.remove(two["id"])
    checked = service.recheck(task["id"])
    gone = next(d for d in checked["detections"] if d["track_id"] == two["id"])
    assert gone["license_snapshot"] == {} and gone["status"] == "待核验"
    with pytest.raises(ValueError, match="任务不存在"):
        service.recheck("missing")


def test_import_rejects_unsupported_silent_and_full_library(env, tmp_path, monkeypatch, media_files):
    paths, store, service = env
    with pytest.raises(ValueError, match="MP3、WAV、FLAC"):
        service.library.import_file(tmp_path / "a.ogg")
    silence = write_wav(tmp_path / "静音.wav", np.zeros(10 * RATE))
    with pytest.raises(ValueError, match="有效指纹"):
        service.library.import_file(silence)
    assert store.tracks() == [] and list(paths.library.iterdir()) == []

    service.library.import_file(media_files["refs"][0])
    monkeypatch.setattr("bgm_audit.fingerprint.MAX_TRACKS", 1)
    with pytest.raises(ValueError, match="上限"):
        service.library.import_file(media_files["refs"][1])
    monkeypatch.setattr("bgm_audit.fingerprint.MAX_REFERENCE_SECONDS", 1)
    with pytest.raises(ValueError, match="过长"):
        service.library.replace_file(store.tracks()[0]["id"], media_files["refs"][1])
    assert list(paths.temp.iterdir()) == []


def test_replace_file_error_paths(env, media_files, tmp_path):
    _, store, service = env
    first = service.library.import_file(media_files["refs"][0])
    second = service.library.import_file(media_files["refs"][1])
    with pytest.raises(ValueError, match="不存在"):
        service.library.replace_file("missing", media_files["refs"][0])
    with pytest.raises(ValueError, match="另一首"):
        service.library.replace_file(first["id"], media_files["refs"][1])
    with pytest.raises(ValueError, match="MP3、WAV、FLAC"):
        service.library.replace_file(first["id"], tmp_path / "a.txt")
    silence = write_wav(tmp_path / "静音.wav", np.zeros(10 * RATE))
    with pytest.raises(ValueError, match="有效指纹"):
        service.library.replace_file(first["id"], silence)
    # 同一音频重新替换：授权状态保留
    service.library.replace_file(second["id"], media_files["refs"][1])
    assert next(t for t in store.tracks() if t["id"] == second["id"])["license"]["status"] == "未提供授权"


def test_missing_vendored_audfprint_is_explicit(monkeypatch, tmp_path):
    from bgm_audit import fingerprint

    monkeypatch.setattr(fingerprint, "ROOT", tmp_path)
    with pytest.raises(RuntimeError, match="audfprint"):
        fingerprint.upstream()


def test_index_is_rebuilt_when_revision_changes(env, media_files):
    paths, store, service = env
    service.library.import_file(media_files["refs"][0])
    from bgm_audit.fingerprint import FingerprintLibrary

    # 另一个进程修改了曲库：缓存的索引版本过期，需按 SQLite 重建。
    other = FingerprintLibrary(paths, store)
    other.ensure_index()
    service.library.import_file(media_files["refs"][1])
    table = other.ensure_index()
    assert len(set(table.names) - {""}) >= 2
    assert other.ensure_index() is table  # 版本未变时复用内存索引


def test_unknown_music_and_noise_do_not_match(real_library, tmp_path):
    _, _, service, _, _ = real_library
    noise = write_wav(tmp_path / "噪声.wav", np.random.default_rng(5).normal(0, 0.3, 10 * RATE))
    other = write_wav(tmp_path / "未入库.wav", music(2024, seconds=10))
    assert service.library.match(noise, 0, 10, Settings()) == []
    assert service.library.match(other, 0, 10, Settings()) == []


def test_temp_files_are_cleaned_when_matching_fails(env, media_files, monkeypatch):
    paths, _, service = env
    service.library.import_file(media_files["refs"][0])

    def explode(*args, **kwargs):
        raise RuntimeError("模拟匹配失败")

    monkeypatch.setattr(service.library, "match", explode)
    task = service.audit(media_files["video"], ["audfprint"], "用途", Settings(local_window=12, local_step=12))
    assert task["status"] == "识别不完整"
    assert [e["kind"] for e in task["errors"]] == ["本地匹配失败", "本地匹配失败"]
    assert task["errors"][0]["start"] == 0 and task["errors"][1]["start"] == 12
    assert list(paths.temp.iterdir()) == []


def test_demo_files_are_original_and_deterministic(tmp_path):
    from bgm_audit.demo import create_demo
    from bgm_audit.fingerprint import digest_file

    first = create_demo(tmp_path / "a")
    second = create_demo(tmp_path / "b")
    names = sorted(p.name for p in first.iterdir())
    assert names == sorted(p.name for p in second.iterdir())
    for name in ("合成音乐_星河.wav", "合成音乐_远山.wav", "合成混合音轨.wav"):
        assert digest_file(first / name) == digest_file(second / name)
    assert 23.9 < probe(first / "演示_双曲漫剧.mp4").duration < 24.2
    with pytest.raises(MediaError):
        probe(first / "演示_无音轨.mov")
    assert Path(first).parent == tmp_path / "a"
