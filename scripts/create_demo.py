"""生成原创合成参考曲和双曲视频；不会联网或自动导入用户曲库。"""
from pathlib import Path
import sys
import wave

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from bgm_audit.config import Paths
from bgm_audit.media import run_ffmpeg


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


def main():
    output = Paths().root/"demo"
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
    print(f"演示文件：{output}")
    print("导入两首 WAV 后，审核 MP4。预期：2–12 秒星河，12–22 秒远山（识别支持区间略短）。")
    print("这些文件由本脚本合成，可自由用于本项目测试，不代表真实商业音乐识别率。")


if __name__ == "__main__":
    main()
