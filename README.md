# 声轨 · 本地漫剧 BGM 版权审核工具

基于 Python 3.12、Streamlit、FFmpeg、audfprint 和 SQLite 的个人使用工具。支持 MP4 / MOV 批量识别、时间段预览、音乐授权登记、人工复查、历史查询及 CSV / JSON 导出。项目代码采用 MIT 许可证。

**默认流程全开源、免费、完全本地运行，不需要 API Key、GPU、云服务器、Docker 或 Redis。** 安装阶段需联网下载依赖，安装完成后的本地指纹识别不发网络请求。Streamlit 的使用统计已关闭，仅监听 `127.0.0.1:8501`。

本地识别只能命中你已导入的参考音乐。软件不附带全球商业音乐指纹库，无法离线凭空得知陌生歌曲名称。对白、强混音、变速、变调、极短片段可能造成漏检或误检。**识别结果及时间区间仅辅助复核，不能代替音乐授权，也不构成法律结论。**

## 安装与启动

### macOS / Linux

在项目目录打开终端：

```bash
chmod +x install.sh start.sh
./install.sh
./start.sh
```

浏览器访问 <http://127.0.0.1:8501>。停止时在终端按 `Ctrl+C`。

安装脚本检测当前系统；优先使用已安装的 [uv](https://docs.astral.sh/uv/getting-started/installation/) 自动安装 Python 3.12 并创建 `.venv`。没有 uv 时需先安装 Python 3.12；Linux 的 Python 还需可用的 venv 模块（Debian / Ubuntu 常为 `python3.12-venv`）。

缺少 FFmpeg 时，macOS 使用 Homebrew，Linux 尝试 apt / dnf / pacman，可能要求本机管理员密码。macOS 没有 Homebrew 时需先安装 Homebrew 再重试；某些 Linux 发行版需要先启用提供完整 FFmpeg 的软件仓库。手动安装也可以，只要 `ffmpeg` 和 `ffprobe` 在 PATH 中。脚本不会安装云服务。

### Windows

在项目目录双击或从终端运行：

```bat
install.bat
start.bat
```

脚本优先使用 uv；否则使用 `py -3.12`，缺失时尝试通过 winget 安装 Python 3.12。FFmpeg 缺失时尝试 `winget install --id Gyan.FFmpeg -e`。系统安装完成后按照提示重新打开终端并再次运行 `install.bat`，以更新 PATH。没有 winget 时，请手动安装 Python 3.12 和 FFmpeg（包括 ffprobe）。启动地址同上。

Windows 脚本使用英文提示以避免不同代码页乱码；软件界面为简体中文。

### 当前开发环境

项目已在当前 Linux 沙盒内安装 Python 3.12 环境和 FFmpeg。可直接：

```bash
cd /data/home/Desktop
./start.sh
```

这台开发沙盒是远程 Linux 电脑；地址 `127.0.0.1` 属于沙盒。如果你要在自己的电脑使用，应复制完整项目（不必复制 `.venv`、`data` 和缓存），在本机运行对应安装脚本。也可在沙盒桌面浏览器访问本地页面。无需公开端口或绑定局域网。

## 使用流程

1. 打开“本地音乐库”，上传或填写 MP3、WAV、FLAC 的本机路径。批量元数据会应用到每个文件；曲名留空使用文件名。导入后逐首编辑创作者、来源和授权材料，也可替换参考音频并重新计算指纹。
2. 录入授权登记状态、授权依据、人工核实状态、覆盖用途及备注。仅“已登记授权”不够，必须同时具备核实、依据和明确用途覆盖，才会产生“授权已核验”。确认期限、平台、地区、改编等条件后再勾选人工核实。
3. 打开“视频审核”，选择多个 MP4 / MOV，保持默认“本地指纹”离线模式。填写当前用途，例如“漫剧商业发布”；用途必须与授权记录中的用途完全一致。
4. 点击“开始批量审核”。任务顺序运行，显示切片级进度；每个视频单独保存结果。没有音轨、曲库为空、损坏文件等会显示具体原因，不会默认为审核成功。
5. 查看命中表，展开每首音乐，检查原始窗口、指纹数量或歌曲标识、授权快照，生成并播放视频片段。原视频也可以在“原视频与人工复查”中加载。
6. 补充备注和人工处理结论，下载 CSV / JSON。历史页面支持按视频名、曲名、歌手和备注检索，并根据最新曲库授权资料重新核验。

路径输入针对**运行该程序的电脑**，不支持从远程电脑直接访问你本机的磁盘。上传模式每个文件默认上限 2 GB，大文件请使用路径方式。处理时会保存原视频副本供复查，因此需预留足够磁盘空间；删除历史任务会同时删除该副本及对应预览，不会删除原始输入文件。

## 识别和时间轴

- FFprobe 检查时长和首个音轨。FFmpeg 将音轨标准化为 16 kHz / 单声道 / PCM16 WAV，按视频起点保留音轨延迟；无音轨明确报错。多音轨视频当前只审核第一个音轨。
- 本地指纹直接调用上游 audfprint 算法：参考音乐生成指纹存入 SQLite，同时创建可重建的 `fingerprints.pklz` 索引。歌曲名称来自参考曲库元数据。
- 默认本地窗口 30 秒、步长 15 秒，启用 `Matcher.find_time_range=True`（即 CLI `--find-time-range`）及精确对齐计数；每个窗口允许多首歌、多次对齐返回，避免只保留整段最高分歌曲。默认至少 15 个对齐指纹、至少 1 秒支持区间。阈值、窗口可在设置中调整。
- 每次本地匹配区间是指纹证据的时间支持范围，通常比歌曲实际区间短；并非精确剪辑边界。原始窗口和对齐偏移保存在报告中。
- 每次匹配都会加回切片在原视频中的起点。切片按 WAV 采样点截取，不从临时片段的零点误报原视频时间。
- 同引擎、同歌曲、相邻扫描且时间接近的结果合并；保留全部原始证据窗口。如果中间窗口未命中或失败，不跨越该窗口合并。
- 临时 WAV 在成功或失败后均自动清理；异常关机遗留文件可在历史页清理。预览视频属于可清理缓存，原视频副本和曲库持久保存。
- 指纹索引采用个人曲库规模参数，常驻约 200 MiB，加上界面和匹配缓冲通常建议至少 2 GB 可用内存；无需 GPU。最多 4095 首参考音乐，单首最多约 6 小时 45 分钟，超出会明确拒绝导入以避免时间字段溢出。大量参考音乐会增加建库、重建时间和哈希碰撞。

## 审核规则

| 情况 | 状态 |
| --- | --- |
| 命中音乐，没有满足条件的授权材料 | 待核验 |
| 本地命中，材料已人工核实、有授权依据、明确覆盖当前用途 | 授权已核验 |
| 登记的授权明确不覆盖当前使用 | 不通过 |
| 成功扫描但没有命中 | 未检出，仍需复核 |
| 任意引擎异常、曲库为空或音轨处理失败 | 识别不完整，并记录具体错误 |
| 不同引擎在重叠区间识别出不同歌曲 | 人工复审 |

任务汇总优先显示“不通过”或“人工复审”，其次是“识别不完整”；无论汇总状态如何，全部错误仍保留和展示。“授权已核验”仅指命中音乐的登记材料经过人工确认，不证明整段视频没有其他未识别音乐。人工结论与自动状态独立保存，复查日志不被备注覆盖。

## 可选 ShazamIO（不属于全流程开源离线模式）

按原始需求提供可选集成，**默认未启用且不在默认安装依赖中**。[ShazamIO 客户端开源](https://github.com/shazamio/ShazamIO)，其调用的 Shazam 服务并不开源；严格要求全流程开源时，只使用本地指纹模式。

如你自行选择使用该联网服务：

```bash
./install.sh --with-shazam
# Windows: install.bat --with-shazam
```

在审核页勾选启用后，可选择“仅 Shazam”或“两者”。不使用付费 API 或 API Key，但该第三方服务的可用性、接口、识别范围与限流不由本项目控制；不能保证永久可用或无限调用。音频特征将发送给 Shazam。

集成固定 ShazamIO 0.9.0，遵循官方示例：

```python
async with Shazam() as shazam:
    response = await shazam.recognize(audio_path)
```

默认 12 秒窗口 / 6 秒步长、至少 2 秒请求间隔、单次超时 25 秒、最多额外重试 2 次。关闭库内部重试，应用控制总尝试次数。失败分类包括网络、超时、429 限流、服务异常和接口变更。当前官方签名建议 12 秒，故窗口限制在 1–12 秒。每个在线结果只标注**切片覆盖估计区间**，不利用返回中的歌曲播放偏移伪造原视频精确入点。保留 key、ISRC、可用链接及 Apple Music ID。

## 数据与备份

默认目录是项目内 `data/`，可在启动前设置 `BGM_DATA_DIR` 为另一个本地目录。重启会继续使用相同数据，不依赖云端账户。

```text
data/
  audit.sqlite3          曲库元数据、指纹、任务、切片证据、授权快照和人工复查日志
  fingerprints.pklz      audfprint 本地索引（由 SQLite 重建）
  library/               导入的参考音乐副本
  videos/                审核视频副本
  previews/              视频片段预览缓存
  temp/                  处理期间临时音频（完成后清理）
  settings.json          扫描设置
```

备份前停止程序，将整个 `data/` 目录复制到本地备份盘。建议使用相同路径恢复；数据库内保存了本地副本的绝对路径，移动到不同目录后，可导出报告作为存档，并重新导入曲库、审核原始视频。本软件仅加载自身产生的指纹索引，不要使用不可信来源的 pickle 索引替换 `fingerprints.pklz`。

## 测试

```bash
# macOS / Linux
.venv/bin/python -m pytest -q

# Windows
.venv\Scripts\python.exe -m pytest -q
```

常规测试不联网：用原创合成音频测试真实 FFmpeg + audfprint；外部 Shazam 识别用 Mock，不把服务不可用当作未命中。覆盖建库、同曲片段、多曲视频、切片时间、合并、无法识别的音频、无音轨视频、网络失败、超时、限流、接口变更、索引恢复、授权规则、CSV/JSON、历史记录以及四个中文页面。

当前验证结果和实机限制见 [测试记录](docs/测试记录.md)。界面示例见 [视频审核](docs/界面_视频审核.png)、[音乐库](docs/界面_音乐库.png)、[历史记录](docs/界面_历史记录.png)。

主动测试真实 Shazam（需要已安装可选依赖、网络连接，以及你有权识别的清晰已知歌曲）：

```bash
BGM_LIVE_AUDIO="/你的路径/歌曲.mp3" .venv/bin/python -m pytest -q -m live
```

```bat
set "BGM_LIVE_AUDIO=C:\Music\歌曲.mp3"
.venv\Scripts\python.exe -m pytest -q -m live
```

未提供 `BGM_LIVE_AUDIO` 时联网测试明确跳过；联网测试遇到服务失败或未识别会失败并说明原因，不宣称识别成功。

生成可以自由测试的双曲演示视频：

```bash
.venv/bin/python scripts/create_demo.py
```

然后在曲库页导入 `data/demo/合成音乐_星河.wav` 和 `合成音乐_远山.wav`，审核 `演示_双曲漫剧.mp4`。视频预期时间：0–2 秒静音、2–12 秒星河、12–22 秒远山、22–24 秒静音。生成的音乐仅用于验证流程，不代表商业音乐样本上的识别率。

## 项目结构与上游

`app.py` 为中文界面；`bgm_audit/media.py` 负责媒体处理；`fingerprint.py` 封装 audfprint；`shazam_engine.py` 负责可选联网识别；`review.py` 负责合并和审核；`storage.py` 负责 SQLite；`service.py` 负责流水线；`reports.py` 导出报告。

audfprint 源码随项目附带，固定提交见 [第三方说明](THIRD_PARTY_NOTICES.md)，无需安装时再访问 GitHub。未附带上游仓库中的商业音乐测试样本，本项目测试使用自生成数据。完整许可证见 `LICENSE` 和各依赖许可证。

## Git 版本管理

项目使用 `main` 作为主分支。Git 记录源码、安装脚本、测试、许可证和示例文档；`.venv/`、`data/`、缓存、日志、密钥配置和 ZIP 发行包不入库。曲库、授权材料和真实视频应按上方“数据与备份”说明单独备份。

查看当前版本和修改：

```bash
git status
git log --oneline -5
git diff
git remote -v
```

修改功能时，建议先创建分支，测试通过后再提交：

```bash
git switch -c feature/功能名称
# 修改代码后运行测试；Windows 改用 .venv\Scripts\python.exe
.venv/bin/python -m pytest -q
git add app.py bgm_audit tests README.md
git diff --cached
git commit -m "feat: 描述本次功能变更"
```

GitHub 登录、远端仓库创建及绑定完成后，可推送当前分支：

```bash
git push -u origin HEAD
```

GitHub 账号与 Codex / ChatGPT 账号相互独立。不要将访问令牌写入项目或提交到 Git，也不要用强制推送覆盖不明来源的远端历史。
