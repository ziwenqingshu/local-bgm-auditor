"""生成原创合成参考曲和双曲视频；不会联网或自动导入用户曲库。"""
from pathlib import Path
import wave

import numpy as np

from .media import run_ffmpeg


def synthesize(seed, seconds=24, rate=16000):
    rng = np.random.default_rng(seed)
    samples = np.zeros(seconds*rate)
    for start in range(0, len(samples), rate//4):
        size = min(rate//4, len(samples)-start)
        t = np.arange(size)/rate
        notes = rng.choice(np.arange(45, 90), 3, replace=False)
        signal = sum(np.sin(2*np.pi*440*2**((n-69)/12)*t+rng.random())
                     + .25*np.sin(2*np.pi*880*2**((n-69)/12)*t) for n in notes)
        samples[start:start+size] = signal*(1-np.exp(-90*t))*np.exp(-5*t)*.15 + rng.normal(0,.1,size)*np.exp(-30*t)
    return samples


def save(path, data):
    with wave.open(str(path), "wb") as out:
        out.setnchannels(1)
        out.setsampwidth(2)
        out.setframerate(16000)
        out.writeframes((np.clip(data, -1, 1)*28000).astype("<i2").tobytes())


def create_demo(root):
    """仅写入指定数据目录内的演示素材。"""
    output = Path(root)/"demo"
    output.mkdir(exist_ok=True)
    one, two = synthesize(123), synthesize(739)
    save(output/"合成音乐_星河.wav", one)
    save(output/"合成音乐_远山.wav", two)
    mixed = np.concatenate([np.zeros(32000), one[64000:224000], two[80000:240000], np.zeros(32000)])
    save(output/"合成混合音轨.wav", mixed)
    run_ffmpeg(["-f", "lavfi", "-i", "color=c=0x163547:s=640x360:r=15:d=24",
                "-i", output/"合成混合音轨.wav", "-c:v", "libx264", "-preset", "ultrafast", "-c:a", "aac",
                "-shortest", output/"演示_双曲漫剧.mp4"])
    run_ffmpeg(["-f", "lavfi", "-i", "color=c=0x163547:s=320x180:r=10:d=3", "-an",
                "-c:v", "libx264", output/"演示_无音轨.mov"])
    return output


def run_demo(service, progress=None):
    """真实离线演示；已有同内容参考曲保持原来的元数据和授权。"""
    from .config import Settings
    from .fingerprint import digest_file

    if progress:
        progress(0, 1, "生成原创演示音乐和视频…")
    output = create_demo(service.paths.root)
    known = {track["sha256"] for track in service.store.tracks()}
    for name in ("星河", "远山"):
        reference = output / f"合成音乐_{name}.wav"
        if digest_file(reference) not in known:
            if progress:
                progress(0, 1, f"正在导入演示音乐：{name}…")
            service.library.import_file(reference, artist="合成演示", source="本项目 create_demo.py 生成的原创测试音频")
    # 演示固定默认设置，不修改用户自定义扫描参数。
    return service.audit(output / "演示_双曲漫剧.mp4", ["audfprint"], "流程演示", Settings(), progress)
