"""启动：.venv/bin/python -m streamlit run app.py --server.address 127.0.0.1"""

import importlib.metadata
import importlib.util
import platform
import shutil
import tempfile
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

import streamlit as st
from filelock import FileLock, Timeout

from bgm_audit.config import Paths, Settings
from bgm_audit.demo import run_demo
from bgm_audit.media import check_ffmpeg, preview_clip, timecode
from bgm_audit.reports import DISCLAIMER, export_csv, export_json
from bgm_audit.service import AuditService
from bgm_audit.storage import Store

st.set_page_config(page_title="声轨 · 漫剧 BGM 审核", page_icon="🎧", layout="wide")
st.markdown(
    """<style>
.block-container {padding-top:4.5rem;max-width:1280px;}
[data-testid="stSidebar"] {border-right:1px solid #dde7ee;}
[data-testid="stMetric"] {background:white;border:1px solid #e1e8ef;border-radius:12px;padding:16px;}
.eyebrow {color:#087f8c;letter-spacing:2px;font-weight:700;font-size:13px;}
[data-testid="stBaseButton-primary"] {border-radius:9px;}
[data-testid="stAppDeployButton"] {display:none;}
</style>""",
    unsafe_allow_html=True,
)


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


def navigate(page):
    st.session_state["page"] = page


def nav_button(label, page, key, primary=False):
    st.button(
        label,
        key=key,
        on_click=navigate,
        args=(page,),
        type="primary" if primary else "secondary",
        width="stretch",
    )


def display_time(value):
    return datetime.fromisoformat(value).astimezone().strftime("%Y-%m-%d %H:%M %Z")


def option_index(options, value, default=0):
    """旧数据或手工编辑的取值不在选项内时回退默认项，而不是让页面崩溃。"""
    return options.index(value) if value in options else default


def home_page():
    heading("从这里开始", "先认识工具，再开始审核", "声轨 · 用自己的参考曲库，找出视频里的配乐，并逐项核对授权。")
    st.info("程序和审核数据保存在运行本工具的电脑上。默认使用完全离线的本地指纹识别。")
    tracks, tasks = store.tracks(), store.tasks()
    a, b, c = st.columns(3)
    a.metric("已导入参考音乐", f"{len(tracks)} 首")
    b.metric("已保存审核记录", f"{len(tasks)} 次")
    c.metric("默认识别模式", "开源 · 离线")
    st.caption("数量包含演示数据；演示结果不代表已审核你的真实素材。")

    st.subheader("第一次使用？先体验一次完整流程")
    with st.container(border=True):
        left, right = st.columns([3, 1])
        left.markdown("**24 秒演示视频 · 两首合成配乐**")
        left.write(
            "点击后自动生成素材、导入参考音乐、执行真实识别。完成后，你可以试听命中片段、填写复查备注并下载报告。"
        )
        left.caption(
            "会在本机保存 2 首演示音乐和 1 次审核记录；已有同内容音乐不会重复导入，也不会覆盖授权。全程不联网。"
        )
        if right.button("一键体验演示", type="primary", width="stretch"):
            try:
                with operation():
                    bar = st.progress(0, text="准备演示…")
                    task = run_demo(
                        service,
                        lambda done, total, message: bar.progress(min(1.0, done / max(total, 1)), text=message),
                    )
                    st.session_state["demo_task"] = task["id"]
                st.rerun()
            except Timeout:
                st.warning("另一个任务正在运行，请完成后再体验演示。")
            except Exception as exc:
                st.error(f"演示未完成：{exc}。请在设置与环境中检查 FFmpeg。")
        demo = store.get_task(st.session_state["demo_task"]) if st.session_state.get("demo_task") else None
        if demo:
            st.success("演示已运行，结果已保存到历史记录。")
            st.caption(
                "预期配乐：2–12 秒「星河」，12–22 秒「远山」。实际识别区间可能略短。默认没有登记授权，命中显示「待核验」是正常的。"
            )
            render_task(demo, "demo_" + demo["id"])

    st.subheader("准备审核自己的视频")
    for col, step, title, description, target, label in zip(  # noqa: B905 - 六组列表等长
        st.columns(3),
        ["01", "02", "03"],
        ["准备参考音乐", "选择视频审核", "复查并导出"],
        [
            "导入可能用到的 MP3、WAV 或 FLAC。曲名、来源和授权材料可以随时补充。",
            "选入 MP4 或 MOV，填写发布用途，点击开始。软件会逐段比对参考曲库。",
            "试听命中片段，核对授权，保存人工处理结论，再下载 CSV 或 JSON 报告。",
        ],
        ["本地音乐库", "视频审核", "历史记录"],
        ["去导入参考音乐", "去审核视频", "去复查报告"],
    ):
        with col, st.container(border=True):
            st.caption(f"步骤 {step}")
            st.markdown(f"### {title}")
            st.write(description)
            nav_button(label, target, "home_step_" + step, primary=(step == "01" and not tracks))

    with st.expander("项目现在能做什么？还有哪些限制？", expanded=True):
        st.markdown(
            "**已实现：** 批量视频审核、多首音乐匹配、出现区间、片段播放、授权登记、人工复查、历史保存及 CSV / JSON 导出。"
        )
        st.markdown("**需要你提供：** 参考音乐文件，以及与发布用途相关的授权材料。歌曲名称来自你登记的曲库信息。")
        st.markdown(
            "**识别范围：** 只能离线识别曲库里已有的歌；未检出仍需复核。对白、变速、变调可能影响识别，时间区间是估计值。目前只处理视频的第一个音轨。"
        )
        st.markdown(
            "**开源免费：** 默认使用 FFmpeg、audfprint、SQLite 和 Streamlit，无付费 API、GPU 或服务器要求。可选 Shazam 服务本身不开源，因此默认关闭。"
        )
    with st.expander("数据在哪里？怎样安装到自己的电脑？"):
        st.write("参考音乐、视频副本、授权信息和历史记录保存在以下数据目录。Git 只管理代码，不备份这些素材。")
        st.code(str(paths.root), language=None)
        st.write(
            "在自己的电脑下载项目后：macOS / Linux 运行 install.sh，再运行 start.sh；Windows 依次运行 install.bat 和 start.bat。"
        )
        st.caption("启动后在运行程序的电脑打开 http://127.0.0.1:8501。安装需要联网下载依赖，离线识别不需要联网。")
        st.link_button("在 GitHub 查看项目与安装说明", "https://github.com/ziwenqingshu/local-bgm-auditor")


def exports(tasks, key):
    col1, col2, _ = st.columns([1, 1, 3])
    col1.download_button("↓ 导出 CSV", export_csv(tasks), "bgm-report.csv", "text/csv", key=f"csv_{key}")
    col2.download_button("↓ 导出 JSON", export_json(tasks), "bgm-report.json", "application/json", key=f"json_{key}")


def render_task(task, key):
    st.subheader(task["filename"])
    st.write(f"**{task['status']}** · 时长 {timecode(task['duration'])} · 用途：{task['purpose']}")
    st.caption(
        f"保存时间：{display_time(task['created_at'])} · 识别来源：{', '.join('本地指纹' if e == 'audfprint' else 'Shazam（联网）' for e in task['engines'])}"
    )
    if task["errors"]:
        st.warning("识别不完整：以下失败区间需要补充识别或人工检查。")
        for err in task["errors"]:
            span = "" if err["start"] is None else f" [{timecode(err['start'])}–{timecode(err['end'])}]"
            st.error(f"{err['engine']} / {err['kind']}{span}：{err['message']}")
    if not task["detections"]:
        st.info("没有音乐命中记录。未检出不代表无音乐或没有版权风险。")
    else:
        st.dataframe(
            [
                {
                    "音乐": d["title"],
                    "歌手": d["artist"],
                    "开始": timecode(d["start"]),
                    "结束": timecode(d["end"]),
                    "来源": "本地指纹" if d["engine"] == "audfprint" else "Shazam（联网）",
                    "区间说明": d["range_kind"],
                    "审核状态": d["status"],
                }
                for d in task["detections"]
            ],
            hide_index=True,
            width="stretch",
        )
        for idx, detection in enumerate(task["detections"]):
            with st.expander(
                f"{detection['title']} · {timecode(detection['start'])}–{timecode(detection['end'])} · 查看证据与播放"
            ):
                st.write(detection["reason"])
                st.caption("区间为识别证据覆盖范围，不代表歌曲的精确入点或出点；请结合原视频复核。")
                st.json(
                    {
                        "原始切片": detection["evidence"],
                        "歌曲标识": detection["identifiers"],
                        "授权快照": detection["license_snapshot"],
                    },
                    expanded=False,
                )
                clip = paths.previews / f"{task['id']}_{idx}.mp4"
                if st.button("生成并播放对应视频片段", key=f"preview_{key}_{idx}"):
                    try:
                        with operation():
                            with st.spinner("正在生成本地预览…"):
                                preview_clip(task["video_path"], clip, detection["start"], detection["end"])
                    except Timeout:
                        st.warning("有识别任务正在运行，请完成后重试")
                    except Exception as exc:
                        st.error(str(exc))
                if clip.is_file():
                    st.video(str(clip))
    st.info("下一步：试听片段 → 核对授权 → 保存人工复查 → 导出报告。自动状态不等于发布许可。")
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
            conclusion = st.selectbox("人工处理结论（独立于自动结果）", options, index=option_index(options, current))
            if st.form_submit_button("保存人工复查"):
                store.review(task["id"], note, conclusion)
                st.success("已保存备注、结论和复查日志")
        if task["reviews"]:
            st.dataframe(
                [
                    {
                        "复查时间": display_time(r["created_at"]),
                        "备注": r["note"],
                        "人工结论": r["conclusion"],
                    }
                    for r in task["reviews"]
                ],
                hide_index=True,
                width="stretch",
            )
        if st.button("用当前曲库授权信息重新核验", key=f"recheck_{key}"):
            service.recheck(task["id"])
            st.rerun()
    exports([store.get_task(task["id"])], key)


def disk_inputs(label, types, key):
    mode = st.radio("文件选择方式", ["选择本地文件", "输入本机文件路径"], horizontal=True, key=f"mode_{key}")
    if mode == "选择本地文件":
        uploaded = st.file_uploader(label, type=types, accept_multiple_files=True, key=f"up_{key}")
        st.caption("文件会传到运行本程序的电脑并保存副本。单个文件上限 2 GB，更大的文件请改用本机路径。")
        return uploaded, []
    raw = st.text_area("每行一个文件完整路径", key=f"paths_{key}", placeholder="/Users/你的名字/Movies/第1集.mp4")
    st.caption("这里的路径属于运行本程序的电脑。")
    return [], [Path(line.strip().strip('"')).expanduser().resolve() for line in raw.splitlines() if line.strip()]


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
    heading("步骤 02 / 03", "视频审核", "先选择视频，再填写用途。审核完成后，向下查看结果、试听片段并保存复查。")
    if not store.tracks():
        st.warning("还没有参考音乐。本地识别需要先建立曲库，否则无法找到视频里的配乐。")
        nav_button("先去导入参考音乐", "本地音乐库", "audit_empty_library")
    st.subheader("1. 选择待审核的视频")
    uploaded, existing = disk_inputs("选择一个或多个漫剧视频", ["mp4", "mov"], "audit")
    st.subheader("2. 确认识别方式与用途")
    st.info("本地指纹模式 · 开源免费 · 只比对已导入的参考音乐")
    engines = ["audfprint"]
    dependency_missing = False
    with st.expander("可选联网识别（不属于全流程开源模式）"):
        shazam_enabled = st.checkbox(
            "启用可选的 Shazam 联网识别",
            value=False,
            help="ShazamIO 客户端开源，但 Shazam 服务并不开源；不属于全流程开源离线模式。",
        )
        engines = ["audfprint"]
        if shazam_enabled:
            st.warning("Shazam 需联网，调用第三方非开源服务；音频特征会发送到 Shazam。严格全流程开源时请关闭。")
            choice = st.radio("识别引擎", ["本地指纹 + Shazam", "仅 Shazam"], horizontal=True)
            engines = ["audfprint", "shazam"] if choice.startswith("本地") else ["shazam"]
            if importlib.util.find_spec("shazamio") is None:
                st.error("未安装可选依赖。请运行 ./install.sh --with-shazam 或 install.bat --with-shazam")
            dependency_missing = importlib.util.find_spec("shazamio") is None
    purpose = st.text_input("本次使用用途", value="漫剧商业发布", help="必须与已核实授权中登记的用途完全一致")
    blocked = (
        not (uploaded or existing)
        or not purpose.strip()
        or dependency_missing
        or ("audfprint" in engines and not store.tracks())
    )
    st.caption("处理后会保存原视频副本与审核结果，可在历史记录中继续复查。")
    if st.button("开始批量审核", type="primary", disabled=blocked):
        bar = st.progress(0, text="准备审核…")
        completed = []
        try:
            with operation(), tempfile.TemporaryDirectory(dir=paths.temp, prefix="upload_") as work:
                sources = materialize(uploaded, existing, Path(work))
                count = len(sources)
                for i, source in enumerate(sources):

                    def update(done, total, message, i=i, name=source.name):
                        bar.progress(
                            min(1.0, (i + done / max(total, 1)) / count),
                            text=f"视频 {i + 1}/{count} · {name} · {message}",
                        )

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
        st.subheader("3. 复查识别结果")
        st.caption("本批次报告包含以下全部视频。每个视频也可单独导出。")
        exports(tasks, "batch")
        for task in tasks:
            render_task(task, "latest_" + task["id"])
            st.divider()


def license_fields(prefix, license_info=None):
    info = license_info or {}
    statuses = ["未提供授权", "授权待核实", "已登记授权"]
    status = st.selectbox(
        "授权登记状态", statuses, index=option_index(statuses, info.get("status")), key=f"ls_{prefix}"
    )
    evidence = st.text_input("授权依据 / 材料位置 / 许可链接", value=info.get("evidence", ""), key=f"le_{prefix}")
    verified = st.checkbox("我已人工核实授权材料", value=info.get("verified") is True, key=f"lv_{prefix}")
    coverages = ["待核实", "覆盖已选用途", "明确不覆盖"]
    coverage = st.selectbox(
        "授权用途覆盖情况", coverages, index=option_index(coverages, info.get("coverage")), key=f"lc_{prefix}"
    )
    purposes = st.text_input(
        "材料覆盖的用途（多个用途用中文分号或英文分号分隔）",
        value="；".join(info.get("purposes", [])),
        key=f"lp_{prefix}",
    )
    note = st.text_area(
        "授权备注（期限、地区、平台、商业使用、改编条件等）", value=info.get("note", ""), key=f"ln_{prefix}"
    )
    return dict(
        status=status,
        evidence=evidence,
        verified=verified,
        coverage=coverage,
        purposes=[p.strip() for p in purposes.replace("；", ";").split(";") if p.strip()],
        note=note,
    )


def library_page():
    heading("步骤 01 / 03", "本地音乐库", "先提供用于比对的参考音乐。导入不是授权证明，材料可以稍后逐首补充。")
    st.caption(f"当前曲库 {len(store.tracks())} 首 · 支持 MP3 / WAV / FLAC")
    import_tab, manage_tab = st.tabs(["① 导入参考音乐", "② 查看音乐与授权"])
    with import_tab:
        uploaded, existing = disk_inputs("选择 MP3 / WAV / FLAC", ["mp3", "wav", "flac"], "library")
        with st.form("import_music"):
            st.caption("以下元数据应用于本批文件；留空曲名会使用各文件名。导入后可逐首编辑。")
            col1, col2 = st.columns(2)
            title = col1.text_input("曲名（可留空）")
            artist = col2.text_input("歌手 / 创作者")
            source = st.text_input("音乐来源", placeholder="购买平台、原作者、开源曲库或素材包名称")
            with st.expander("填写授权材料（可稍后补充）"):
                st.caption("暂时留空会登记为「未提供授权」，命中后提示待核验。")
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
                        progress.progress((idx + 1) / len(sources))
            except Timeout:
                st.warning("正在执行其他本地任务，请稍后重试")
        if store.tracks():
            st.success("曲库已可用于比对。你可以继续导入，或进入下一步。")
            nav_button("下一步：审核视频 →", "视频审核", "library_next", primary=True)
    with manage_tab:
        tracks = store.tracks()
        if not tracks:
            st.info("曲库尚为空。先导入你有权用于比对的参考音乐，再开始离线审核。")
            return
        st.dataframe(
            [
                {
                    "曲名": t["title"],
                    "创作者": t["artist"],
                    "来源": t["source"],
                    "时长": timecode(t["duration"]),
                    "授权登记": t["license"]["status"],
                    "已人工核实": t["license"].get("verified", False),
                }
                for t in tracks
            ],
            hide_index=True,
            width="stretch",
        )
        selected = st.selectbox(
            "选择要编辑的音乐",
            [t["id"] for t in tracks],
            format_func=lambda value: next(
                f"{t['title']} · {t['artist']} · {value[:8]}" for t in tracks if t["id"] == value
            ),
        )
        track = next(t for t in tracks if t["id"] == selected)
        with st.form("edit_" + selected):
            title = st.text_input("曲名", track["title"])
            artist = st.text_input("创作者", track["artist"])
            source = st.text_input("来源", track["source"])
            license_info = license_fields("edit_" + selected, track["license"])
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
            replacement = st.file_uploader("选择新的参考音频", type=["mp3", "wav", "flac"], key="replace_" + selected)
            if st.button("更新音频与指纹", disabled=replacement is None):
                try:
                    with (
                        operation(),
                        tempfile.TemporaryDirectory(dir=paths.temp, prefix="upload_replace_") as work,
                    ):
                        files = materialize([replacement], [], Path(work))
                        service.library.replace_file(selected, files[0])
                    st.success("参考音频和指纹已更新，请核对授权材料")
                    st.rerun()
                except Timeout:
                    st.warning("本地任务运行中，请稍后重试")
                except Exception as exc:
                    st.error(str(exc))
        confirmed = st.checkbox(
            "确认删除这首参考音乐及指纹（历史识别证据保留）", key="delete_track_confirm_" + selected
        )
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
    heading("步骤 03 / 03", "历史记录", "查询音乐命中、补充审核备注，或根据最新授权材料重新核验。")
    query = st.text_input("搜索视频名称、曲名、歌手或审核备注")
    rows = store.tasks(query)
    if not rows:
        st.info("没有符合条件的历史记录。完成审核后，结果会自动保存在这里。")
        nav_button("去审核视频", "视频审核", "history_empty")
    else:
        st.dataframe(
            [
                {
                    "视频": r["filename"],
                    "状态": r["status"],
                    "用途": r["purpose"],
                    "人工结论": r["conclusion"],
                    "保存时间": display_time(r["created_at"]),
                }
                for r in rows
            ],
            hide_index=True,
            width="stretch",
        )
        exports([store.get_task(r["id"]) for r in rows], "all_history")
        task_id = st.selectbox(
            "查看任务",
            [r["id"] for r in rows],
            format_func=lambda value: next(
                f"{r['filename']} · {display_time(r['created_at'])} · {value[:8]}" for r in rows if r["id"] == value
            ),
        )
        task = store.get_task(task_id)
        render_task(task, "history_" + task_id)
        st.divider()
        confirm = st.checkbox("确认删除该任务、保存的视频副本和预览文件", key="delete_task_" + task_id)
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
    heading("高级设置", "设置与环境", "所有数据保存在本机目录；识别服务仅监听 127.0.0.1。")
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
                config = Settings(
                    shazam_window,
                    shazam_step,
                    request_interval,
                    request_timeout,
                    retries,
                    local_window,
                    local_step,
                    min_hashes,
                    min_match_seconds,
                    merge_gap,
                )
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
    st.write("Streamlit：" + importlib.metadata.version("streamlit"))
    st.write(
        "ShazamIO（可选）："
        + (importlib.metadata.version("shazamio") if importlib.util.find_spec("shazamio") else "未安装")
    )
    st.caption("安装脚本只需联网下载开源依赖。本地指纹运行不需要联网、API Key、GPU、Docker 或云服务。")


with st.sidebar:
    st.markdown("## ♪ 声轨")
    st.caption("漫剧 BGM 识别与授权复核")
    page = st.radio(
        "工作台",
        ["开始使用", "本地音乐库", "视频审核", "历史记录", "设置与环境"],
        key="page",
        label_visibility="collapsed",
        format_func=lambda name: {
            "开始使用": "开始使用 · 项目概览",
            "本地音乐库": "① 本地音乐库",
            "视频审核": "② 视频审核",
            "历史记录": "③ 历史记录",
        }.get(name, name),
    )
    st.divider()
    st.markdown("**本地优先 · 开源免费**")
    st.caption("FFmpeg / audfprint / SQLite / Streamlit")
    st.caption("识别到歌曲不等于已获得授权。")

{
    "开始使用": home_page,
    "视频审核": audit_page,
    "本地音乐库": library_page,
    "历史记录": history_page,
    "设置与环境": settings_page,
}[page]()
st.divider()
st.caption(DISCLAIMER)
