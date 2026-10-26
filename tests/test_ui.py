from pathlib import Path

import streamlit as st
from streamlit.testing.v1 import AppTest


def test_chinese_pages_render_without_exceptions(tmp_path, monkeypatch):
    st.cache_resource.clear()
    monkeypatch.setenv("BGM_DATA_DIR", str(tmp_path / "ui_data"))
    app = AppTest.from_file(str(Path(__file__).resolve().parent.parent / "app.py"), default_timeout=120)
    app.run()
    assert not app.exception
    assert app.title[0].value == "先认识工具，再开始审核"
    app.button(key="home_step_01").click().run()
    assert app.title[0].value == "本地音乐库"
    for name in ("本地音乐库", "历史记录", "设置与环境", "视频审核"):
        app.sidebar.radio[0].set_value(name).run()
        assert not app.exception
        assert app.title[0].value == name
    assert next(b for b in app.button if b.label == "开始批量审核").disabled
    st.cache_resource.clear()


def test_populated_library_and_history_render(real_library, media_files, monkeypatch):
    from bgm_audit.config import Settings

    paths, store, service, _, _ = real_library
    task = service.audit(media_files["video"], ["audfprint"], "漫剧商业发布", Settings())
    store.review(task["id"], "界面测试复查", "已人工复核")
    monkeypatch.setenv("BGM_DATA_DIR", str(paths.root))
    st.cache_resource.clear()

    app = AppTest.from_file(str(Path(__file__).resolve().parent.parent / "app.py"), default_timeout=120)
    app.run()
    for name in ("本地音乐库", "历史记录"):
        app.sidebar.radio[0].set_value(name).run()
        assert not app.exception
        assert len(app.dataframe) >= 1
    st.cache_resource.clear()


def test_guided_demo_real_recognition_review_preview_and_export(tmp_path, monkeypatch):
    from bgm_audit.config import Paths
    from bgm_audit.reports import export_csv, export_json
    from bgm_audit.storage import Store

    monkeypatch.setenv("BGM_DATA_DIR", str(tmp_path / "demo_data"))
    st.cache_resource.clear()
    app = AppTest.from_file(str(Path(__file__).resolve().parent.parent / "app.py"), default_timeout=300)
    app.run()
    next(b for b in app.button if b.label == "一键体验演示").click().run()
    assert not app.exception
    store = Store(Paths())
    task = store.get_task(store.tasks()[0]["id"])
    assert len(store.tracks()) == 2
    assert {d["title"] for d in task["detections"]} == {"合成音乐_星河", "合成音乐_远山"}
    assert task["status"] == "待核验"
    assert not task["errors"]
    next(b for b in app.button if b.label == "生成并播放对应视频片段").click().run()
    assert not app.exception
    assert app.get("video")
    next(t for t in app.text_area if t.label == "审核备注").set_value("已试听，待补材料")
    next(b for b in app.button if b.label == "保存人工复查").click().run()
    assert not app.exception
    assert app.get("video"), "预览应在表单保存后保留"
    task = store.get_task(task["id"])
    assert task["note"] == "已试听，待补材料"
    assert "已试听，待补材料" in export_csv([task]).decode("utf-8-sig")
    assert "已试听，待补材料" in export_json([task]).decode("utf-8")
    # 再次演示不会覆盖用户编辑过的曲目资料，也不会重复建库。
    track = store.tracks()[0]
    store.update_track(track["id"], track["title"], "用户编辑", "用户来源", track["license"])
    next(b for b in app.button if b.label == "一键体验演示").click().run()
    assert not app.exception
    assert len(store.tracks()) == 2
    assert next(t for t in store.tracks() if t["id"] == track["id"])["artist"] == "用户编辑"
    assert len(store.tasks()) == 2
    st.cache_resource.clear()
