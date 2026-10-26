from pathlib import Path

from streamlit.testing.v1 import AppTest
import streamlit as st


def test_chinese_pages_render_without_exceptions(tmp_path, monkeypatch):
    st.cache_resource.clear()
    monkeypatch.setenv("BGM_DATA_DIR", str(tmp_path/"ui_data"))
    app = AppTest.from_file(str(Path(__file__).resolve().parent.parent/"app.py"), default_timeout=30)
    app.run()
    assert not app.exception
    assert app.title[0].value == "视频审核"
    for name in ("本地音乐库", "历史记录", "设置与环境", "视频审核"):
        app.sidebar.radio[0].set_value(name).run()
        assert not app.exception
        assert app.title[0].value == name


def test_populated_library_and_history_render(real_library, media_files, monkeypatch):
    from bgm_audit.config import Settings
    paths, store, service, _, _ = real_library
    task = service.audit(media_files["video"], ["audfprint"], "漫剧商业发布", Settings())
    store.review(task["id"], "界面测试复查", "已人工复核")
    monkeypatch.setenv("BGM_DATA_DIR", str(paths.root))
    st.cache_resource.clear()
    app = AppTest.from_file(str(Path(__file__).resolve().parent.parent/"app.py"), default_timeout=30)
    app.run()
    for name in ("本地音乐库", "历史记录"):
        app.sidebar.radio[0].set_value(name).run()
        assert not app.exception
        assert len(app.dataframe) >= 1
    st.cache_resource.clear()
