"""启动：.venv/bin/python -m streamlit run app.py --server.address 127.0.0.1"""
from contextlib import contextmanager
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
import importlib.metadata
import importlib.util
import platform
import shutil
import tempfile

from filelock import FileLock, Timeout
import streamlit as st

from bgm_audit.config import Paths, Settings
from bgm_audit.media import check_ffmpeg, preview_clip, timecode
from bgm_audit.reports import DISCLAIMER, export_csv, export_json
from bgm_audit.service import AuditService
from bgm_audit.storage import Store

st.set_page_config(page_title="声轨 · 漫剧 BGM 审核", page_icon="🎧", layout="wide")
st.markdown("""<style>
.block-container {padding-top:4.5rem;max-width:1280px;}
[data-testid="stSidebar"] {border-right:1px solid #dde7ee;}
[data-testid="stMetric"] {background:white;border:1px solid #e1e8ef;border-radius:12px;padding:16px;}
.eyebrow {color:#087f8c;letter-spacing:3px;font-weight:700;font-size:12px;}
[data-testid="stAppDeployButton"] {display:none;}
</style>""", unsafe_allow_html=True)


@st.cache_resource
def resources():
    paths = Paths()
    store = Store(paths)
    return paths, store, AuditService(paths, store)


paths, store, service = resources()


@contextmanager
def operation():
    """串行化 UI 的写入任务和清理，避免同时删除识别中的文件。"""
    with FileLock(paths.root / "operation.lock", timeout=0):
        yield


def heading(label, title, description):
    st.markdown(f'<div class="eyebrow">{label}</div>', unsafe_allow_html=True)
    st.title(title)
    st.caption(description)


def exports(tasks, key):
    col1, col2, _ = st.columns([1, 1, 3])
    col1.download_button("↓ 导出 CSV", export_csv(tasks), "bgm-report.csv", "text/csv", key=f"csv_{key}")
    col2.download_button("↓ 导出 JSON", export_json(tasks), "bgm-report.json", "application/json", key=f"json_{key}")


def render_task(task, key):
    st.subheader(task["filename"])
    st.write(f'**{task["status"]}** · 时长 {timecode(task["duration"])} · 用途：{task["purpose"]}')
    st.caption(f'任务 {task["id"][:12]} · {task["created_at"]} · 原始引擎：{", ".join(task["engines"])}')
    if task["errors"]:
        st.warning("识别不完整：以下失败区间需要补充识别或人工检查。")
        for err in task["errors"]:
            span = "" if err["start"] is None else f' [{timecode(err["start"])}–{timecode(err["end"])}]'
            st.error(f'{err["engine"]} / {err["kind"]}{span}：{err["message"]}')
    if not task["detections"]:
        st.info("没有音乐命中记录。未检出不代表无音乐或没有版权风险。")
    else:
        st.dataframe([{
            "音乐": d["title"], "歌手": d["artist"], "开始": timecode(d["start"]),
            "结束": timecode(d["end"]), "来源": "本地指纹" if d["engine"] == "audfprint" else "Shazam（联网）",
            "区间说明": d["range_kind"], "审核状态": d["status"]
        } for d in task["detections"]], hide_index=True, width="stretch")
        for idx, detection in enumerate(task["detections"]):
            with st.expander(f'{detection["title"]} · {timecode(detection["start"])}–{timecode(detection["end"])} · 查看证据与播放'):
                st.write(detection["reason"])
                st.caption("区间为识别证据覆盖范围，不代表歌曲的精确入点或出点；请结合原视频复核。")
                st.json({"原始切片": detection["evidence"], "歌曲标识": detection["identifiers"],
                         "授权快照": detection["license_snapshot"]}, expanded=False)
                if st.button("生成并播放对应视频片段", key=f"preview_{key}_{idx}"):
                    try:
                        with operation():
                            clip = paths.previews / f'{task["id"]}_{idx}.mp4'
                            with st.spinner("正在生成本地预览…"):
                                preview_clip(task["video_path"], clip, detection["start"], detection["end"])
                            st.video(str(clip))
                    except Timeout:
                        st.warning("有识别任务正在运行，请完成后重试")
                    except Exception as exc:
                        st.error(str(exc))
    with st.expander("原视频与人工复查", expanded=False):
        if st.checkbox("加载完整原视频", key=f"full_{key}"):
            video = Path(task["video_path"])
            if video.is_file():
                st.video(str(video))
            else:
                st.warning("本地视频副本已不存在")
        with st.form(f"review_{key}"):
            note = st.text_area("审核备注", value=task["note"])
            options = ["未处理", "待补充授权", "已人工复核", "替换音乐", "确认不通过"]
            current = task["conclusion"] or "未处理"
            conclusion = st.selectbox("人工处理结论（独立于自动结果）", options,
                                       index=options.index(current) if current in options else 0)
            if st.form_submit_button("保存人工复查"):
                store.review(task["id"], note, conclusion)
                st.success("已保存备注、结论和复查日志")
        if task["reviews"]:
            st.dataframe(task["reviews"], hide_index=True, width="stretch")
        if st.button("用当前曲库授权信息重新核验", key=f"recheck_{key}"):
            service.recheck(task["id"])
            st.rerun()
    exports([store.get_task(task["id"])], key)


def disk_inputs(label, types, key):
    mode = st.radio("文件选择方式", ["选择本地文件", "输入本机文件路径"], horizontal=True, key=f"mode_{key}")
    if mode == "选择本地文件":
        uploaded = st.file_uploader(label, type=types, accept_multiple_files=True, key=f"up_{key}")
        st.caption("文件只发送到运行本工具的电脑，不上传到云端。大于 2 GB 的视频请使用路径方式。")
        return uploaded, []
    raw = st.text_area("每行一个文件完整路径", key=f"paths_{key}", placeholder="/Users/你的名字/Movies/第1集.mp4")
    st.caption("这里的路径属于运行程序的电脑。如果当前使用远程沙盒，需先将文件传入沙盒。")
    return [], [Path(line.strip().strip('\"')).expanduser().resolve() for line in raw.splitlines() if line.strip()]


def materialize(uploaded, existing, directory):
    result = list(existing)
    for index, file in enumerate(uploaded):
        # 隔离目录保留原文件名，避免同名文件互相覆盖和路径穿越。
        subdir = directory / str(index)
        subdir.mkdir()
        name = file.name.replace("\\", "/").rsplit("/", 1)[-1]
        target = subdir / name
        with target.open("wb") as out:
            out.write(file.getbuffer())
        result.append(target)
    return result


def audit_page():
    heading("LOCAL AUDIO REVIEW", "视频审核", "逐段识别背景音乐，保留每一段识别证据。默认使用完全离线的本地曲库。")
    a, b, c = st.columns(3)
    a.metric("本地参考音乐", f"{len(store.tracks())} 首")
    b.metric("历史审核", f"{len(store.tasks())} 次")
    c.metric("默认工作方式", "完全离线")
    st.write("")
    uploaded, existing = disk_inputs("选择一个或多个漫剧视频", ["mp4", "mov"], "audit")
    shazam_enabled = st.checkbox("启用可选的 Shazam 联网识别", value=False,
                                 help="ShazamIO 客户端开源，但 Shazam 服务并不开源；不属于全流程开源离线模式。")
    engines = ["audfprint"]
    if shazam_enabled:
        st.warning("Shazam 需联网，调用第三方非开源服务；音频特征会发送到 Shazam。严格全流程开源时请关闭。")
        choice = st.radio("识别引擎", ["本地指纹 + Shazam", "仅 Shazam"], horizontal=True)
        engines = ["audfprint", "shazam"] if choice.startswith("本地") else ["shazam"]
        if importlib.util.find_spec("shazamio") is None:
            st.error("未安装可选依赖。请运行 ./install.sh --with-shazam 或 install.bat --with-shazam")
    else:
        st.info("本地指纹模式 · 全部识别在本机执行 · 只识别已导入曲库中的参考音乐")
    purpose = st.text_input("本次使用用途", value="漫剧商业发布", help="必须与已核实授权中登记的用途完全一致")
    if st.button("开始批量审核", type="primary", disabled=not (uploaded or existing)):
        bar = st.progress(0, text="准备审核…")
        completed = []
        try:
            with operation(), tempfile.TemporaryDirectory(dir=paths.temp, prefix="upload_") as work:
                sources = materialize(uploaded, existing, Path(work))
                for i, source in enumerate(sources):
                    def update(done, total, message):
                        bar.progress(min(1.0, (i+done/max(total, 1))/len(sources)),
                                     text=f"视频 {i+1}/{len(sources)} · {source.name} · {message}")
                    try:
                        task = service.audit(source, engines, purpose, paths.load_settings(), update)
                        completed.append(task["id"])
                    except Exception as exc:
                        st.error(f"{source.name}：{exc}")
                st.session_state["latest_tasks"] = completed
                bar.progress(1.0, text="本批次处理完成")
        except Timeout:
            st.warning("另一个页面正在执行识别或导入，请稍后重试")
    tasks = [store.get_task(t) for t in st.session_state.get("latest_tasks", [])]
    tasks = [t for t in tasks if t]
    if tasks:
        st.divider()
        exports(tasks, "batch")
        for task in tasks:
            render_task(task, "latest_"+task["id"])
            st.divider()


def license_fields(prefix, license_info=None):
    info = license_info or {}
    statuses = ["未提供授权", "授权待核实", "已登记授权"]
    status = st.selectbox("授权登记状态", statuses,
                          index=statuses.index(info.get("status", statuses[0])), key=f"ls_{prefix}")
    evidence = st.text_input("授权依据 / 材料位置 / 许可链接", value=info.get("evidence", ""), key=f"le_{prefix}")
    verified = st.checkbox("我已人工核实授权材料", value=info.get("verified", False), key=f"lv_{prefix}")
    coverages = ["待核实", "覆盖已选用途", "明确不覆盖"]
    coverage = st.selectbox("授权用途覆盖情况", coverages,
                            index=coverages.index(info.get("coverage", "待核实")), key=f"lc_{prefix}")
    purposes = st.text_input("材料覆盖的用途（多个用途用中文分号或英文分号分隔）",
                             value="；".join(info.get("purposes", [])), key=f"lp_{prefix}")
    note = st.text_area("授权备注（期限、地区、平台、商业使用、改编条件等）",
                         value=info.get("note", ""), key=f"ln_{prefix}")
    return dict(status=status, evidence=evidence, verified=verified, coverage=coverage,
                purposes=[p.strip() for p in purposes.replace("；", ";").split(";") if p.strip()], note=note)


def library_page():
    heading("REFERENCE LIBRARY", "本地音乐库", "导入参考音乐并生成音频指纹。授权登记与歌曲识别相互独立。")
    with st.expander("＋ 批量导入参考音乐", expanded=True):
        uploaded, existing = disk_inputs("选择 MP3 / WAV / FLAC", ["mp3", "wav", "flac"], "library")
        with st.form("import_music"):
            st.caption("以下元数据应用于本批文件；留空曲名会使用各文件名。导入后可逐首编辑。")
            col1, col2 = st.columns(2)
            title = col1.text_input("曲名（可留空）")
            artist = col2.text_input("歌手 / 创作者")
            source = st.text_input("音乐来源", placeholder="购买平台、原作者、开源曲库或素材包名称")
            license_info = license_fields("import")
            submit = st.form_submit_button("导入并创建指纹", type="primary", disabled=not (uploaded or existing))
        if submit:
            try:
                with operation(), tempfile.TemporaryDirectory(dir=paths.temp, prefix="upload_music_") as work:
                    sources = materialize(uploaded, existing, Path(work))
                    progress = st.progress(0)
                    for idx, path in enumerate(sources):
                        try:
                            with st.spinner(f"正在为 {path.name} 计算指纹…"):
                                service.library.import_file(path, title, artist, source, license_info)
                            st.success(f"已导入：{path.name}")
                        except Exception as exc:
                            st.error(f"{path.name}：{exc}")
                        progress.progress((idx+1)/len(sources))
            except Timeout:
                st.warning("正在执行其他本地任务，请稍后重试")
    tracks = store.tracks()
    if not tracks:
        st.info("曲库尚为空。先导入你有权用于比对的参考音乐，再开始离线审核。")
        return
    st.dataframe([{"曲名": t["title"], "创作者": t["artist"], "来源": t["source"],
                   "时长": timecode(t["duration"]), "授权登记": t["license"]["status"],
                   "已人工核实": t["license"].get("verified", False)} for t in tracks],
                 hide_index=True, width="stretch")
    selected = st.selectbox("选择要编辑的音乐", [t["id"] for t in tracks],
                            format_func=lambda value: next(f'{t["title"]} · {t["artist"]} · {value[:8]}' for t in tracks if t["id"] == value))
    track = next(t for t in tracks if t["id"] == selected)
    with st.form("edit_"+selected):
        title = st.text_input("曲名", track["title"])
        artist = st.text_input("创作者", track["artist"])
        source = st.text_input("来源", track["source"])
        license_info = license_fields("edit_"+selected, track["license"])
        if st.form_submit_button("保存音乐与授权信息"):
            if not title.strip():
                st.error("曲名不能为空")
            else:
                store.update_track(selected, title.strip(), artist, source, license_info)
                st.success("已保存。历史任务可点击重新核验以应用新授权信息。")
    if Path(track["path"]).is_file():
        st.audio(track["path"])
    else:
        st.warning("参考音频副本不存在，可在下方更新参考音频")
    with st.expander("更新参考音频并重新计算指纹"):
        st.caption("保留曲名和授权材料；文件内容变化会自动将授权改为待核实。历史识别证据保留。")
        replacement = st.file_uploader("选择新的参考音频", type=["mp3", "wav", "flac"], key="replace_"+selected)
        if st.button("更新音频与指纹", disabled=replacement is None):
            try:
                with operation(), tempfile.TemporaryDirectory(dir=paths.temp, prefix="upload_replace_") as work:
                    files = materialize([replacement], [], Path(work))
                    service.library.replace_file(selected, files[0])
                st.success("参考音频和指纹已更新，请核对授权材料")
                st.rerun()
            except Timeout:
                st.warning("本地任务运行中，请稍后重试")
            except Exception as exc:
                st.error(str(exc))
    confirmed = st.checkbox("确认删除这首参考音乐及指纹（历史识别证据保留）", key="delete_track_confirm_"+selected)
    if st.button("删除参考音乐", disabled=not confirmed):
        try:
            with operation():
                service.library.remove(selected)
            st.rerun()
        except Timeout:
            st.warning("本地任务运行中，请稍后重试")
    if st.button("从 SQLite 重建指纹索引"):
        try:
            with operation(), st.spinner("正在重建…"):
                service.library.rebuild()
            st.success("已重建")
        except Timeout:
            st.warning("本地任务运行中，请稍后重试")


def history_page():
    heading("AUDIT HISTORY", "历史记录", "查询音乐命中、补充审核备注，或根据最新授权材料重新核验。")
    query = st.text_input("搜索视频名称、曲名、歌手或审核备注")
    rows = store.tasks(query)
    if not rows:
        st.info("没有符合条件的历史记录")
    else:
        st.dataframe([{"视频": r["filename"], "状态": r["status"], "用途": r["purpose"],
                       "人工结论": r["conclusion"], "时间 UTC": r["created_at"]} for r in rows],
                     hide_index=True, width="stretch")
        exports([store.get_task(r["id"]) for r in rows], "all_history")
        task_id = st.selectbox("查看任务", [r["id"] for r in rows],
                               format_func=lambda value: next(f'{r["filename"]} · {r["created_at"][:19]} · {value[:8]}' for r in rows if r["id"] == value))
        task = store.get_task(task_id)
        render_task(task, "history_"+task_id)
        st.divider()
        confirm = st.checkbox("确认删除该任务、保存的视频副本和预览文件", key="delete_task_"+task_id)
        if st.button("删除历史任务", disabled=not confirm):
            try:
                with operation():
                    store.delete_task(task_id)
                st.rerun()
            except Timeout:
                st.warning("任务正在执行，请稍后再删除")
    with st.expander("本地文件清理"):
        st.caption("常规处理会自动清理临时音频。此处清理异常退出留下的临时文件和全部预览缓存；曲库和历史视频保留。")
        if st.button("清理临时文件与预览缓存"):
            try:
                with operation():
                    for directory in (paths.temp, paths.previews):
                        for target in directory.iterdir():
                            if target.is_dir():
                                shutil.rmtree(target)
                            else:
                                target.unlink()
                st.success("清理完成")
            except Timeout:
                st.warning("识别或导入正在运行，完成后才能清理")


def settings_page():
    heading("LOCAL SETTINGS", "设置与环境", "所有数据保存在本机目录；识别服务仅监听 127.0.0.1。")
    config = paths.load_settings()
    with st.form("settings"):
        st.subheader("本地指纹扫描")
        a, b = st.columns(2)
        local_window = a.number_input("本地窗口（秒）", 2.0, 120.0, config.local_window)
        local_step = b.number_input("本地步长（秒）", 1.0, 120.0, config.local_step)
        min_hashes = a.number_input("最低对齐指纹数量", 5, 1000, config.min_hashes)
        min_match_seconds = b.number_input("最短匹配支持区间（秒）", 0.1, 30.0, config.min_match_seconds)
        merge_gap = st.number_input("同曲区间合并容差（秒）", 0.0, 10.0, config.merge_gap)
        st.subheader("可选 Shazam 参数")
        st.caption("仅在视频审核页手动启用后生效，默认不用联网引擎。")
        shazam_window = a.number_input("Shazam 窗口（秒）", 1.0, 12.0, config.shazam_window, step=1.0)
        shazam_step = b.number_input("Shazam 步长（秒）", 1.0, 12.0, config.shazam_step, step=1.0)
        request_interval = a.number_input("最小请求间隔（秒）", 0.0, 60.0, config.request_interval)
        request_timeout = b.number_input("单次超时（秒）", 1.0, 120.0, config.request_timeout)
        retries = st.number_input("额外重试次数", 0, 5, config.retries)
        if st.form_submit_button("保存设置", type="primary"):
            try:
                config = Settings(shazam_window, shazam_step, request_interval, request_timeout, retries,
                                  local_window, local_step, min_hashes, min_match_seconds, merge_gap)
                paths.save_settings(config)
                st.success("已保存")
            except ValueError as exc:
                st.error(str(exc))
    st.subheader("环境检查")
    st.write(f"操作系统：{platform.system()} {platform.release()} · Python {platform.python_version()}")
    st.code(str(paths.root), language=None)
    try:
        check_ffmpeg()
        st.success("FFmpeg / ffprobe 可用")
    except Exception as exc:
        st.error(str(exc))
    st.write("Streamlit："+importlib.metadata.version("streamlit"))
    st.write("ShazamIO（可选）："+(importlib.metadata.version("shazamio") if importlib.util.find_spec("shazamio") else "未安装"))
    st.caption("安装脚本只需联网下载开源依赖。本地指纹运行不需要联网、API Key、GPU、Docker 或云服务。")


with st.sidebar:
    st.markdown("## ♪ 声轨")
    st.caption("漫剧 BGM 识别与授权复核")
    page = st.radio("工作台", ["视频审核", "本地音乐库", "历史记录", "设置与环境"], label_visibility="collapsed")
    st.divider()
    st.markdown("**本地优先 · 开源免费**")
    st.caption("FFmpeg / audfprint / SQLite / Streamlit")
    st.caption("识别到歌曲不等于已获得授权。")

{"视频审核": audit_page, "本地音乐库": library_page,
 "历史记录": history_page, "设置与环境": settings_page}[page]()
st.divider()
st.caption(DISCLAIMER)
