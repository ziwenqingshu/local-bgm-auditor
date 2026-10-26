from pathlib import Path

import numpy as np
import pytest

from bgm_audit.config import Settings
from bgm_audit.media import run_ffmpeg, slice_wav
from conftest import write_wav, music


def test_import_creates_reference_and_fingerprint_index(real_library):
    paths, store, service, one, two = real_library
    assert len(store.tracks()) == 2
    assert paths.index.stat().st_size > 100
    assert Path(one["path"]).is_file()
    assert len(store.tracks(include_hashes=True)[0]["hashes"]) > 100


def test_same_song_excerpt_matches(real_library, media_files, tmp_path):
    _, _, service, one, _ = real_library
    clip = slice_wav(media_files["refs"][0], tmp_path/"excerpt.wav", 4, 14)
    found = service.library.match(clip, 32, 42, Settings())
    hit = next(d for d in found if d.track_id == one["id"])
    assert 32 <= hit.start < 34
    assert 40 < hit.end <= 42
    assert hit.evidence[0]["window_start"] == 32
    assert hit.evidence[0]["aligned_hashes"] >= 15


def test_video_contains_multiple_songs_with_correct_times(real_library, media_files):
    paths, store, service, one, two = real_library
    config = Settings(local_window=8, local_step=4)
    progress = []
    task = service.audit(media_files["video"], ["audfprint"], "漫剧商业发布", config,
                         lambda done, total, message: progress.append((done, total)))
    assert task["errors"] == []
    ids = {d["track_id"] for d in task["detections"]}
    assert {one["id"], two["id"]} <= ids
    for d in task["detections"]:
        if d["track_id"] == one["id"]:
            assert 1.5 < d["start"] < d["end"] < 12.5
            assert d["status"] == "授权已核验"
        else:
            assert 11.5 < d["start"] < d["end"] < 22.5
            assert d["status"] == "待核验"
        assert all(0 <= e["window_start"] < e["window_end"] <= 24 for e in d["evidence"])
    assert progress[-1][0] == progress[-1][1]
    assert store.get_task(task["id"])["detections"] == task["detections"]
    assert list(paths.temp.iterdir()) == []


def test_one_large_window_returns_more_than_top_song(real_library, media_files):
    _, _, service, one, two = real_library
    found = service.library.match(media_files["audio"], 0, 24, Settings())
    assert {one["id"], two["id"]} <= {d.track_id for d in found}


def test_unrecognizable_silence(real_library, tmp_path):
    _, _, service, _, _ = real_library
    silence = write_wav(tmp_path/"silence.wav", np.zeros(8*16000))
    assert service.library.match(silence, 0, 8, Settings()) == []


def test_duplicate_import_rejected(real_library, media_files):
    _, store, service, _, _ = real_library
    with pytest.raises(ValueError, match="已在曲库"):
        service.library.import_file(media_files["refs"][0])
    assert len(store.tracks()) == 2


@pytest.mark.parametrize("extension", ["mp3", "flac"])
def test_import_supported_formats_and_delete(env, media_files, tmp_path, extension):
    paths, store, service = env
    encoded = tmp_path/f"reference.{extension}"
    run_ffmpeg(["-i", media_files["refs"][0], encoded])
    track = service.library.import_file(encoded)
    assert len(store.tracks()) == 1
    service.library.remove(track["id"])
    assert store.tracks() == []
    assert not Path(track["path"]).exists()
    assert paths.index.exists()


def test_index_recovers_from_damage(real_library):
    paths, store, service, one, two = real_library
    paths.index.write_bytes(b"broken index")
    from bgm_audit.fingerprint import FingerprintLibrary
    fresh = FingerprintLibrary(paths, store)
    table = fresh.ensure_index()
    assert {one["id"], two["id"]} <= set(table.names)


def test_replace_reference_recalculates_fingerprints(env, media_files, tmp_path):
    _, store, service = env
    original = service.library.import_file(media_files["refs"][0], license_info={
        "status": "已登记授权", "verified": True, "evidence": "测试授权依据"})
    replacement = write_wav(tmp_path/"updated.wav", music(919))
    service.library.replace_file(original["id"], replacement)
    updated = store.tracks()[0]
    assert updated["id"] == original["id"]
    assert updated["sha256"] != original["sha256"]
    assert updated["license"]["status"] == "授权待核实"
    assert updated["license"]["verified"] is False
    assert not Path(original["path"]).exists()
    found = service.library.match(replacement, 0, 24, Settings())
    assert any(d.track_id == original["id"] for d in found)


def test_unknown_music_video_is_unmatched_not_approved(real_library, media_files, tmp_path):
    _, _, service, _, _ = real_library
    unknown = write_wav(tmp_path/"unknown.wav", music(446))
    video = tmp_path/"unknown.mp4"
    run_ffmpeg(["-f", "lavfi", "-i", "color=s=160x90:r=10:d=24", "-i", unknown,
                "-c:v", "libx264", "-preset", "ultrafast", "-c:a", "aac", "-shortest", video])
    task = service.audit(video, ["audfprint"], "发布", Settings())
    assert task["detections"] == []
    assert task["errors"] == []
    assert task["status"] == "未检出，仍需复核"
