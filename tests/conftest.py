import wave

import numpy as np
import pytest

from bgm_audit.config import Paths
from bgm_audit.media import run_ffmpeg
from bgm_audit.service import AuditService
from bgm_audit.storage import Store


def write_wav(path, data, rate=16000):
    with wave.open(str(path), "wb") as out:
        out.setnchannels(1)
        out.setsampwidth(2)
        out.setframerate(rate)
        out.writeframes((np.clip(data, -1, 1) * 28000).astype("<i2").tobytes())
    return path


def music(seed, seconds=24, rate=16000):
    """可重复的原创合成旋律和打击声，不下载或分发商业歌曲。"""
    rng = np.random.default_rng(seed)
    result = np.zeros(seconds * rate)
    step = rate // 4
    for pos in range(0, len(result), step):
        n = min(step, len(result) - pos)
        t = np.arange(n) / rate
        notes = rng.choice(np.arange(45, 90), 3, replace=False)
        envelope = (1 - np.exp(-t * 90)) * np.exp(-t * 5)
        signal = sum(
            np.sin(2 * np.pi * 440 * 2 ** ((note - 69) / 12) * t + rng.random())
            + 0.25 * np.sin(2 * np.pi * 880 * 2 ** ((note - 69) / 12) * t)
            for note in notes
        )
        drums = rng.normal(0, 0.10, n) * np.exp(-t * 30)
        result[pos : pos + n] += signal * envelope * 0.15 + drums
    return result


@pytest.fixture(scope="session")
def media_files(tmp_path_factory):
    root = tmp_path_factory.mktemp("original_media")
    first, second = music(123), music(739)
    refs = [write_wav(root / "星河.wav", first), write_wav(root / "远山.wav", second)]
    rate = 16000
    # 原视频时间轴：0-2 静音，2-12 星河，12-22 远山，22-24 静音。
    mixed = np.concatenate(
        [np.zeros(2 * rate), first[4 * rate : 14 * rate], second[5 * rate : 15 * rate], np.zeros(2 * rate)]
    )
    audio = write_wav(root / "mixed.wav", mixed)
    video = root / "两首配乐.mp4"
    run_ffmpeg(
        [
            "-f",
            "lavfi",
            "-i",
            "color=c=navy:s=320x180:r=10:d=24",
            "-i",
            audio,
            "-c:v",
            "libx264",
            "-preset",
            "ultrafast",
            "-c:a",
            "aac",
            "-shortest",
            video,
        ]
    )
    silent_video = root / "无音轨.mov"
    run_ffmpeg(["-f", "lavfi", "-i", "color=s=160x90:r=10:d=2", "-an", "-c:v", "libx264", silent_video])
    return dict(root=root, refs=refs, first=first, second=second, audio=audio, video=video, silent_video=silent_video)


@pytest.fixture
def env(tmp_path):
    paths = Paths(tmp_path / "data")
    store = Store(paths)
    return paths, store, AuditService(paths, store)


@pytest.fixture(scope="module")
def real_library(tmp_path_factory, media_files):
    paths = Paths(tmp_path_factory.mktemp("fingerprint_library"))
    store = Store(paths)
    service = AuditService(paths, store)
    verified = dict(
        status="已登记授权",
        verified=True,
        coverage="覆盖已选用途",
        purposes=["漫剧商业发布"],
        evidence="原创合成测试音乐",
        note="测试用途",
    )
    one = service.library.import_file(media_files["refs"][0], "星河", "合成创作者甲", "测试合成", verified)
    two = service.library.import_file(media_files["refs"][1], "远山", "合成创作者乙", "测试合成")
    return paths, store, service, one, two
