import wave

import numpy as np
import pytest

from bgm_audit.media import NoAudioError, extract_audio, probe, run_ffmpeg, slice_wav, windows


def test_windows_cover_timeline_without_extra_tail():
    assert windows(25, 12, 6) == [(0, 12), (6, 18), (12, 24), (18, 25)]
    assert windows(12, 12, 6) == [(0, 12)]
    assert windows(3, 12, 6) == [(0, 3)]
    with pytest.raises(ValueError):
        windows(5, 2, 3)


def test_sample_accurate_slice_and_video_timeline(media_files, tmp_path):
    wav = extract_audio(media_files["video"], tmp_path / "full.wav")
    clip = slice_wav(wav, tmp_path / "clip.wav", 12, 18)
    with wave.open(str(wav)) as full, wave.open(str(clip)) as part:
        full.setpos(12 * 16000)
        assert part.getnframes() == 6 * 16000
        assert part.readframes(6 * 16000) == full.readframes(6 * 16000)


def test_delayed_audio_stream_preserves_video_origin(media_files, tmp_path):
    delayed = tmp_path / "delayed.mp4"
    run_ffmpeg(
        [
            "-f",
            "lavfi",
            "-i",
            "color=s=160x90:r=10:d=6",
            "-itsoffset",
            2,
            "-i",
            media_files["refs"][0],
            "-t",
            6,
            "-c:v",
            "libx264",
            "-c:a",
            "aac",
            delayed,
        ]
    )
    info = probe(delayed)
    assert 1.8 < info.audio_offset < 2.1
    wav = extract_audio(delayed, tmp_path / "aligned.wav", info)
    with wave.open(str(wav)) as reader:
        signal = np.frombuffer(reader.readframes(reader.getnframes()), dtype="<i2")
    assert np.max(np.abs(signal[: int(1.8 * 16000)])) == 0
    assert np.max(np.abs(signal[int(2.2 * 16000) :])) > 100


def test_no_audio_error_is_explicit(media_files):
    with pytest.raises(NoAudioError, match="没有音轨"):
        probe(media_files["silent_video"])
