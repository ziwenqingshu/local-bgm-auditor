from dataclasses import dataclass
from pathlib import Path
import json
import math
import shutil
import subprocess
import wave


class MediaError(RuntimeError):
    pass


class NoAudioError(MediaError):
    pass


@dataclass(frozen=True)
class MediaInfo:
    duration: float
    audio_codec: str
    sample_rate: int
    channels: int
    audio_offset: float = 0.0


def check_ffmpeg():
    missing = [name for name in ("ffmpeg", "ffprobe") if not shutil.which(name)]
    if missing:
        raise MediaError("缺少 " + "、".join(missing) + "，请先运行安装脚本并重启终端")


def run_ffmpeg(args, timeout=600):
    check_ffmpeg()
    try:
        result = subprocess.run(["ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error",
                                 "-y", *map(str, args)], capture_output=True,
                                text=True, encoding="utf-8", errors="replace", timeout=timeout)
    except subprocess.TimeoutExpired as exc:
        raise MediaError("FFmpeg 处理超时；请缩短视频或检查文件") from exc
    if result.returncode:
        raise MediaError("FFmpeg 处理失败：" + result.stderr[-1500:])


def probe(path):
    check_ffmpeg()
    path = Path(path).resolve()
    if not path.is_file():
        raise MediaError("文件不存在：" + str(path))
    try:
        result = subprocess.run(["ffprobe", "-v", "error", "-show_format", "-show_streams",
                                 "-of", "json", str(path)], capture_output=True, text=True,
                                encoding="utf-8", errors="replace", timeout=30, check=True)
        data = json.loads(result.stdout)
    except (subprocess.SubprocessError, ValueError) as exc:
        raise MediaError("无法读取媒体信息，文件可能损坏或格式不支持") from exc
    audio = next((s for s in data.get("streams", []) if s.get("codec_type") == "audio"), None)
    if audio is None:
        raise NoAudioError("该视频没有音轨，无法识别背景音乐")
    video = next((s for s in data.get("streams", []) if s.get("codec_type") == "video"), None)
    fmt = data.get("format", {})
    duration = float(fmt.get("duration") or audio.get("duration") or 0)
    if not math.isfinite(duration) or duration <= 0:
        raise MediaError("无法读取有效时长")
    origin = float((video or {}).get("start_time") or fmt.get("start_time") or 0)
    offset = float(audio.get("start_time") or origin) - origin if video else 0.0
    return MediaInfo(duration, audio.get("codec_name", "未知"),
                     int(audio.get("sample_rate", 0)), int(audio.get("channels", 0)), offset)


def extract_audio(source, target, info=None):
    """PCM16 / 16kHz / 单声道，保留首音轨相对视频起点的延迟。"""
    info = info or probe(source)
    filters = ["aresample=16000", "asetpts=PTS-STARTPTS"]
    if info.audio_offset > 0:
        filters.append(f"adelay={round(info.audio_offset * 16000)}S:all=1")
    elif info.audio_offset < 0:
        filters += [f"atrim=start={-info.audio_offset:.6f}", "asetpts=PTS-STARTPTS"]
    filters += ["apad", f"atrim=duration={info.duration:.6f}"]
    run_ffmpeg(["-i", Path(source).resolve(), "-map", "0:a:0", "-vn", "-af", ",".join(filters),
                "-ac", 1, "-ar", 16000, "-c:a", "pcm_s16le", target],
               timeout=max(600, info.duration * 2))
    return Path(target)


def windows(duration, window, step):
    if not (duration > 0 and 0 < step <= window):
        raise ValueError("无效的时长或切片参数")
    result = []
    index = 0
    while True:
        start = round(index * step, 6)
        end = min(duration, start + window)
        result.append((start, end))
        if end >= duration - 1e-6:
            break
        index += 1
    return result


def slice_wav(source, target, start, end):
    """从已标准化的 WAV 精确按采样点切片，原始时间由调用方保存。"""
    if start < 0 or end <= start:
        raise MediaError("切片起止时间无效")
    with wave.open(str(source), "rb") as src:
        rate = src.getframerate()
        first = min(src.getnframes(), round(start * rate))
        last = min(src.getnframes(), round(end * rate))
        src.setpos(first)
        with wave.open(str(target), "wb") as dst:
            dst.setparams(src.getparams())
            dst.writeframes(src.readframes(last - first))
    return Path(target)


def preview_clip(source, target, start, end):
    """兼容 MOV/HEVC 的短 MP4 预览，无需保留临时识别音频。"""
    run_ffmpeg(["-ss", max(0, start), "-i", Path(source).resolve(), "-t", max(0.1, end-start),
                "-map", "0:v:0?", "-map", "0:a:0?", "-vf", "scale=960:540:force_original_aspect_ratio=decrease:force_divisible_by=2",
                "-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p",
                "-c:a", "aac", "-movflags", "+faststart", target])
    return Path(target)


def timecode(seconds):
    total = max(0, round(seconds * 1000))
    return f"{total//3600000:02d}:{total//60000%60:02d}:{total//1000%60:02d}.{total%1000:03d}"
