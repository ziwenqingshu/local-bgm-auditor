# 参与贡献

感谢你愿意改进声轨！欢迎提交 Issue 和 Pull Request。中文或英文都可以。

## 原则

- **默认流程必须保持本地、离线、免费**：不要引入付费服务、API Key、遥测或默认联网的功能。联网能力只能作为默认关闭的可选项。
- **不要提交任何真实音乐、视频或个人数据**。测试素材请用 `tests/conftest.py` 里的 `music()` / `write_wav()` 等合成函数生成；`.gitignore` 已排除常见音视频格式和 `data/`。
- 识别结果宁可「待核验」也不要「误报通过」：修改审核规则时请同步更新 README 的规则表和 `tests/test_rules.py`。

## 开发环境

```bash
./install.sh --dev           # Windows: install.bat --dev
.venv/bin/pre-commit install # 提交前自动运行 ruff、mypy、gitleaks
```

需要 Python 3.12 和 FFmpeg（含 ffprobe）。

## 提交前检查

```bash
.venv/bin/ruff check .
.venv/bin/ruff format --check .
.venv/bin/mypy
.venv/bin/python -m pytest -q --cov=bgm_audit
```

CI 会在 Ubuntu、macOS、Windows 上运行同样的检查，`bgm_audit/` 覆盖率低于 85% 会失败。修复 bug 时请附带能复现问题的回归测试。

## 提交与 PR

- 使用 [Conventional Commits](https://www.conventionalcommits.org/zh-hans/)：`feat:`、`fix:`、`docs:`、`test:`、`refactor:`、`build:`、`ci:`、`chore:`。
- 从 `main` 创建分支，一个 PR 只做一件事，在描述中说明动机和验证方式。
- 面向用户的变化请在 `CHANGELOG.md` 的 `[Unreleased]` 下记录。
- `vendor/audfprint` 是上游源码的逐字节副本，请不要直接修改；需要的行为差异放在 `bgm_audit/fingerprint.py` 的封装层。

## 报告问题

请使用 Issue 模板，附上操作系统、Python 和 FFmpeg 版本（`python scripts/check_environment.py` 的输出）。**不要上传受版权保护的音乐或包含个人信息的视频**；如需复现，尽量用合成素材或描述文件特征（编码、时长、音轨数量）。

安全问题请按 [SECURITY.md](SECURITY.md) 私下报告。
