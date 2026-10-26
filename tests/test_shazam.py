import asyncio
import os
from unittest.mock import AsyncMock

import pytest

from bgm_audit.config import Settings
from bgm_audit.media import extract_audio
from bgm_audit.shazam_engine import ShazamScanner, client_factory, parse_response


class FakeShazam:
    def __init__(self, responses):
        self.recognize = AsyncMock(side_effect=responses)
        self.closed = False

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        self.closed = True


def config(**kwargs):
    return Settings(request_interval=0, request_timeout=1, retries=0, **kwargs)


def test_real_response_parsing_and_window_estimates():
    d = parse_response({"track": {"key": "123", "title": "曲名", "subtitle": "歌手", "isrc": "ISRC-123"}}, 18, 30, 3)
    assert d.track_id == "123" and d.identifiers["isrc"] == "ISRC-123"
    assert (d.start, d.end) == (18, 30)
    assert d.evidence == [dict(segment_index=3, window_start=18, window_end=30)]
    assert "估计" in d.range_kind


def test_network_failure_is_incomplete_and_client_closes(media_files, tmp_path):
    fake = FakeShazam([OSError("network unreachable")])
    found, errors = asyncio.run(ShazamScanner(config(), lambda: fake).scan(media_files["audio"], [(6, 18)], tmp_path))
    assert found == []
    assert errors[0].kind == "网络失败" and errors[0].start == 6
    assert errors[0].attempts == 1 and fake.closed
    assert not (tmp_path / "shazam.wav").exists()


def test_limited_retry_then_success(media_files, tmp_path, monkeypatch):
    fake = FakeShazam([OSError("offline"), {"track": {"key": "1", "title": "曲"}}])
    monkeypatch.setattr("bgm_audit.shazam_engine.asyncio.sleep", AsyncMock())
    settings = config()
    settings.retries = 1
    found, errors = asyncio.run(ShazamScanner(settings, lambda: fake).scan(media_files["audio"], [(0, 12)], tmp_path))
    assert len(found) == 1 and not errors
    assert fake.recognize.await_count == 2 and fake.closed


@pytest.mark.parametrize("response,expected", [({"matches": []}, None), ({"unexpected": "changed"}, "接口变更")])
def test_no_match_vs_protocol_change(media_files, tmp_path, response, expected):
    fake = FakeShazam([response])
    found, errors = asyncio.run(ShazamScanner(config(), lambda: fake).scan(media_files["audio"], [(0, 12)], tmp_path))
    assert not found
    assert (errors[0].kind if errors else None) == expected
    assert fake.closed


@pytest.mark.parametrize("error,kind", [(TimeoutError(), "超时"), (RuntimeError("HTTP 429"), "服务限流")])
def test_timeout_and_rate_limit(media_files, tmp_path, error, kind):
    fake = FakeShazam([error])
    found, errors = asyncio.run(ShazamScanner(config(), lambda: fake).scan(media_files["audio"], [(0, 12)], tmp_path))
    assert errors[0].kind == kind and fake.closed


def test_factory_closes_real_shazam_client_without_network():
    pytest.importorskip("shazamio")

    async def check():
        async with client_factory() as client:
            assert callable(client.recognize)

    asyncio.run(check())


@pytest.mark.live
def test_live_shazam_with_user_provided_music(tmp_path):
    source = os.environ.get("BGM_LIVE_AUDIO")
    if not source:
        pytest.skip("主动设置 BGM_LIVE_AUDIO 为你有权用于识别的音乐路径才联网测试")
    pytest.importorskip("shazamio")
    audio = extract_audio(source, tmp_path / "live.wav")
    settings = Settings(retries=1)
    found, errors = asyncio.run(ShazamScanner(settings).scan(audio, [(0, 12)], tmp_path))
    assert not errors, [e.to_dict() for e in errors]
    assert found, "接口正常但未命中；请选择 Shazam 曲库内的清晰音乐片段"
    assert found[0].title and "估计" in found[0].range_kind
