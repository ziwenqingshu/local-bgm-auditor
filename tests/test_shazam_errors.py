"""可选 Shazam 引擎的错误分类和响应解析；全部 Mock，不联网。"""

import asyncio
import builtins
from unittest.mock import AsyncMock

import pytest
from test_shazam import FakeShazam

from bgm_audit.config import Settings
from bgm_audit.shazam_engine import (
    ProtocolError,
    ShazamScanner,
    classify_error,
    client_factory,
    parse_response,
)


class ContentTypeError(Exception):
    pass


class ClientConnectorError(Exception):
    pass


class HTTPError(Exception):
    status = 429


@pytest.mark.parametrize(
    ("error", "kind"),
    [
        (TimeoutError(), "超时"),
        (HTTPError("too many"), "服务限流"),
        (ProtocolError("坏结构"), "接口变更"),
        (ContentTypeError("text/html"), "接口变更"),
        (ConnectionResetError("reset"), "网络失败"),
        (ClientConnectorError("dns"), "网络失败"),
        (RuntimeError("未安装可选 ShazamIO"), "依赖缺失"),
        (ValueError("boom"), "服务异常"),
    ],
)
def test_error_classification(error, kind):
    assert classify_error(error)[0] == kind


@pytest.mark.parametrize(
    "response",
    ["not a dict", {"track": {"subtitle": "无名"}}, {"track": "字符串"}, {"matches": "x"}],
)
def test_malformed_responses_are_protocol_errors(response):
    with pytest.raises(ProtocolError):
        parse_response(response, 0, 12, 0)


def test_identifiers_include_apple_music_id_and_fallback_track_id():
    response = {
        "track": {
            "title": "曲",
            "subtitle": "人",
            "url": "https://example.invalid/t",
            "hub": {"options": [{"actions": [{"type": "applemusicplay", "id": "999"}]}]},
        }
    }
    found = parse_response(response, 6, 18, 1)
    assert found.identifiers == {"url": "https://example.invalid/t", "apple_music_id": "999"}
    assert found.track_id == "曲|人"


def test_protocol_change_is_not_retried(media_files, tmp_path, monkeypatch):
    fake = FakeShazam([{"unexpected": True}, {"track": {"key": "1", "title": "x"}}])
    monkeypatch.setattr("bgm_audit.shazam_engine.asyncio.sleep", AsyncMock())
    settings = Settings(request_interval=0, retries=3)
    found, errors = asyncio.run(ShazamScanner(settings, lambda: fake).scan(media_files["audio"], [(0, 12)], tmp_path))
    assert not found and errors[0].kind == "接口变更" and errors[0].attempts == 1
    assert fake.recognize.await_count == 1


def test_request_interval_is_respected_between_windows(media_files, tmp_path, monkeypatch):
    sleeps = []

    async def fake_sleep(delay):
        sleeps.append(delay)

    monkeypatch.setattr("bgm_audit.shazam_engine.asyncio.sleep", fake_sleep)
    fake = FakeShazam([{"matches": []}, {"matches": []}])
    settings = Settings(request_interval=5, retries=0)
    progress = []
    asyncio.run(
        ShazamScanner(settings, lambda: fake).scan(
            media_files["audio"], [(0, 12), (6, 18)], tmp_path, lambda *a: progress.append(a)
        )
    )
    assert len(sleeps) == 1 and 4 < sleeps[0] <= 5
    assert [p[0] for p in progress] == [1, 2]


def test_client_creation_failure_is_recorded(media_files, tmp_path):
    def broken():
        raise RuntimeError("未安装可选 ShazamIO；运行安装脚本的 --with-shazam 模式")

    found, errors = asyncio.run(ShazamScanner(Settings(), broken).scan(media_files["audio"], [(0, 12)], tmp_path))
    assert not found and errors[0].kind == "依赖缺失" and errors[0].start is None


def test_missing_optional_dependency_message(monkeypatch):
    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name.startswith("shazamio"):
            raise ImportError(name)
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    with pytest.raises(RuntimeError, match="--with-shazam"):
        client_factory()


def test_audit_with_both_engines_flags_conflicts(real_library, media_files):
    _, _, service, _, _ = real_library
    fake = FakeShazam([{"track": {"key": "x", "title": "完全不同的歌", "subtitle": "某人"}}] * 10)
    task = service.audit(
        media_files["video"],
        ["audfprint", "shazam"],
        "漫剧商业发布",
        Settings(request_interval=0, retries=0),
        shazam_factory=lambda: fake,
    )
    assert task["status"] == "人工复审"
    assert {d["engine"] for d in task["detections"]} == {"audfprint", "shazam"}
