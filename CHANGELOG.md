# Changelog

本项目遵循 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/) 与 [语义化版本](https://semver.org/lang/zh-CN/)。

## [Unreleased]

## [0.1.0] - 2026-10-26

首个公开版本。

### 新增

- 离线 BGM 识别：FFmpeg 音轨标准化 + 上游 audfprint 指纹匹配，支持 MP4 / MOV 批量审核、单窗口多曲、相邻窗口合并。
- 本地音乐库：MP3 / WAV / FLAC 导入、元数据与授权登记、参考音频替换、索引重建。
- 授权规则：待核验 / 授权已核验 / 不通过 / 人工复审 / 识别不完整 / 未检出，并保存授权快照。
- 人工复查日志（含状态快照）、历史检索、按最新授权重新核验、CSV / JSON 导出（防公式注入）。
- 一键离线演示：合成两首原创音乐和 24 秒视频，走完整识别、预览、复查和导出流程。
- 可选 ShazamIO 联网识别（默认关闭），带限速、超时、有限重试和错误分类。
- 工程化：`pyproject.toml` 元数据、ruff（lint + format）、mypy（strict，`bgm_audit/`）、pre-commit、GitHub Actions（Ubuntu / macOS / Windows × Python 3.12，覆盖率报告，gitleaks 全历史扫描）、可选 Dockerfile。
- 文档：README（中文 / English）、架构概览、真实运行截图与 GIF、CONTRIBUTING、SECURITY、第三方许可证说明、Issue / PR 模板。

### 修复

- 授权「明确不覆盖」的命中在与另一引擎冲突时会被降级为「人工复审」，掩盖拒绝结论；现在「不通过」始终保留。
- 授权记录中的 `verified` 必须严格为 `true`，手工编辑成字符串 `"false"` 不再被当作已核实。
- 用途首尾空白会导致已核验授权匹配失败；现在比较前去除首尾空白。
- 历史搜索未转义 `%` / `_`，输入它们会匹配全部任务。
- `settings.json` 中出现其他版本的字段时会把全部设置重置为默认值；空的 `BGM_DATA_DIR` 会把数据写到当前工作目录。
- 数据目录不存在时 `create_demo` 失败。
- FFprobe 返回 `N/A` 等非数字字段时抛出未处理的异常。
- CSV 防注入补充制表符 / 回车前缀，且不再给负数等数值单元格加引号。
- 旧数据中未知的授权状态 / 覆盖取值会导致音乐库页面崩溃。

### 测试

- 测试数从 36 个增至 150 个，`bgm_audit/` 分支覆盖率从 90%（语句）提升到约 97–98%；新增边界用例：无音轨、空 / 损坏 / 截断文件、空曲库、多音轨、音轨早于 / 晚于画面、两首歌叠加、合并规则、README 审核规则表、存储迁移等。

[Unreleased]: https://github.com/ziwenqingshu/local-bgm-auditor/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/ziwenqingshu/local-bgm-auditor/releases/tag/v0.1.0
