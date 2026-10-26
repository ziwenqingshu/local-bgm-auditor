"""对官方 audfprint 的薄封装，SQLite 保存可重建指纹索引的数据。"""
from contextlib import redirect_stdout
from pathlib import Path
import gzip
import hashlib
import importlib
import io
import os
import shutil
import sys
import tempfile
import uuid

from filelock import FileLock
import numpy as np

from .config import ROOT
from .media import extract_audio, probe
from .models import Detection

MAX_REFERENCE_SECONDS = ((1 << 20) - 1) * 256 / 11025
MAX_TRACKS = 4095

def upstream():
    directory = ROOT / "vendor" / "audfprint"
    if not (directory / "audfprint_analyze.py").is_file():
        raise RuntimeError("缺少 audfprint 源码，请重新运行 install 脚本")
    if str(directory) not in sys.path:
        sys.path.insert(0, str(directory))
    return (importlib.import_module("audfprint_analyze"),
            importlib.import_module("audfprint_match"), importlib.import_module("hash_table"))


def encode_hashes(hashes):
    out = io.BytesIO()
    np.save(out, np.asarray(hashes, dtype=np.int32), allow_pickle=False)
    return out.getvalue()


def decode_hashes(blob):
    return np.load(io.BytesIO(blob), allow_pickle=False)


def digest_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as src:
        for block in iter(lambda: src.read(1024*1024), b""):
            h.update(block)
    return h.hexdigest()


class FingerprintLibrary:
    def __init__(self, paths, store):
        self.paths, self.store = paths, store
        self._table = None
        self._revision = -1
        self._lock = FileLock(self.paths.lock, timeout=300)

    def lock(self):
        return self._lock

    def _rebuild(self):
        _, _, ht = upstream()
        # 与官方默认 hashbits 相同；约 200 MiB，不需要 GPU。
        table = ht.HashTable(hashbits=20, depth=50, maxtime=1 << 20)
        for track in self.store.tracks(include_hashes=True):
            table.store(track["id"], decode_hashes(track["hashes"]))
        revision = self.store.revision()
        table.params["library_revision"] = revision
        target = self.paths.root / "fingerprints.tmp.pklz"
        try:
            with gzip.open(target, "wb") as file:
                with redirect_stdout(io.StringIO()):
                    table.save(str(target), file_object=file)
            os.replace(target, self.paths.index)
        finally:
            target.unlink(missing_ok=True)
        self._table, self._revision = table, revision
        return table

    def ensure_index(self):
        with self.lock():
            revision = self.store.revision()
            if self._table is not None and self._revision == revision and self.paths.index.exists():
                return self._table
            _, _, ht = upstream()
            if self.paths.index.exists():
                try:
                    with redirect_stdout(io.StringIO()):
                        table = ht.HashTable(str(self.paths.index))
                    if table.params.get("library_revision") == revision:
                        self._table, self._revision = table, revision
                        return table
                except Exception:
                    # 索引中断或版本变更时，用 SQLite 中的指纹重建。
                    pass
            return self._rebuild()

    def import_file(self, path, title="", artist="", source="", license_info=None):
        path = Path(path).resolve()
        if path.suffix.lower() not in (".mp3", ".wav", ".flac"):
            raise ValueError("参考音乐仅支持 MP3、WAV、FLAC")
        info = probe(path)
        if info.duration >= MAX_REFERENCE_SECONDS:
            raise ValueError("单首参考音乐超过约 6 小时 45 分钟，请先拆成较短文件")
        digest = digest_file(path)
        track_id = uuid.uuid4().hex
        destination = self.paths.library / f"{track_id}{path.suffix.lower()}"
        with self.lock():
            if len(self.store.tracks()) >= MAX_TRACKS:
                raise ValueError("个人曲库上限为 4095 首，请删除不再需要的参考音乐")
            if any(t["sha256"] == digest for t in self.store.tracks()):
                raise ValueError("该文件已在曲库中，请编辑已有记录")
            analyze, _, _ = upstream()
            analyzer = analyze.Analyzer()
            analyzer.shifts = 1
            with tempfile.TemporaryDirectory(dir=self.paths.temp, prefix="import_") as work:
                wav = extract_audio(path, Path(work) / "reference.wav", info)
                hashes = analyzer.wavfile2hashes(str(wav))
            if len(hashes) < 5:
                raise ValueError("音频中没有足够的有效指纹，可能是静音或片段过短")
            track = dict(id=track_id, title=title.strip() or path.stem, artist=artist.strip(),
                         source=source.strip(), path=str(destination), sha256=digest,
                         duration=info.duration, license=license_info or {
                             "status": "未提供授权", "verified": False, "coverage": "待核实",
                             "purposes": [], "evidence": "", "note": ""})
            shutil.copy2(path, destination)
            try:
                self.store.add_track(track, encode_hashes(hashes))
            except Exception:
                destination.unlink(missing_ok=True)
                raise
            # SQLite 是事实来源；索引写入失败时，下次 ensure_index 可修复。
            self._rebuild()
        return track

    def remove(self, track_id):
        with self.lock():
            self.store.remove_track(track_id)
            self._rebuild()

    def replace_file(self, track_id, path):
        """保留歌曲 ID 与授权登记，替换参考音频并重新生成指纹。"""
        path = Path(path).resolve()
        if path.suffix.lower() not in (".mp3", ".wav", ".flac"):
            raise ValueError("参考音乐仅支持 MP3、WAV、FLAC")
        info = probe(path)
        if info.duration >= MAX_REFERENCE_SECONDS:
            raise ValueError("参考音乐过长，请拆分后导入")
        digest = digest_file(path)
        with self.lock():
            tracks = self.store.tracks()
            original = next((t for t in tracks if t["id"] == track_id), None)
            if original is None:
                raise ValueError("参考音乐不存在")
            if any(t["sha256"] == digest and t["id"] != track_id for t in tracks):
                raise ValueError("该音频已属于曲库中的另一首音乐")
            analyze, _, _ = upstream()
            analyzer = analyze.Analyzer()
            analyzer.shifts = 1
            with tempfile.TemporaryDirectory(dir=self.paths.temp, prefix="replace_") as directory:
                wav = extract_audio(path, Path(directory)/"reference.wav", info)
                hashes = analyzer.wavfile2hashes(str(wav))
            if len(hashes) < 5:
                raise ValueError("音频中没有足够的有效指纹")
            destination = self.paths.library/f"{track_id}_{uuid.uuid4().hex}{path.suffix.lower()}"
            shutil.copy2(path, destination)
            license_info = dict(original["license"])
            if digest != original["sha256"]:
                license_info.update(status="授权待核实", verified=False)
            try:
                self.store.replace_track_audio(track_id, destination, digest, info.duration,
                                               encode_hashes(hashes), license_info)
            except Exception:
                destination.unlink(missing_ok=True)
                raise
            old = Path(original["path"]).resolve()
            if old.is_relative_to(self.paths.library):
                old.unlink(missing_ok=True)
            self._rebuild()

    def rebuild(self):
        with self.lock():
            return self._rebuild()

    def match(self, audio_path, window_start, window_end, settings, segment_index=0):
        with self.lock():
            table = self.ensure_index()
            tracks = {t["id"]: t for t in self.store.tracks()}
            if not tracks:
                return []
            analyze, match, _ = upstream()
            analyzer = analyze.Analyzer()
            analyzer.shifts = 4
            matcher = match.Matcher()
            matcher.find_time_range = True
            matcher.exact_count = True
            matcher.time_quantile = 0.02
            matcher.threshcount = settings.min_hashes
            matcher.max_returns = max(20, len(tracks)*4)
            matcher.search_depth = max(100, len(tracks))
            matcher.window = 2
            rows, _, query_hashes = matcher.match_file(analyzer, table, str(audio_path))
            hop = analyzer.n_hop / analyzer.target_sr
            result = []
            for row in rows:
                idx, score, skew, raw, rank, first, last = map(int, row)
                track = tracks.get(table.names[idx])
                start = max(window_start, window_start + first*hop)
                end = min(window_end, window_start + last*hop)
                if not track or end-start < settings.min_match_seconds:
                    continue
                evidence = dict(segment_index=segment_index, window_start=window_start,
                                window_end=window_end, match_start=start, match_end=end,
                                aligned_hashes=score, query_hashes=query_hashes,
                                reference_offset_seconds=skew*hop)
                result.append(Detection("audfprint", track["id"], track["title"], track["artist"],
                                        round(start, 6), round(end, 6), "指纹支持区间（估计）",
                                        [evidence], license_snapshot=track["license"]))
            return result
