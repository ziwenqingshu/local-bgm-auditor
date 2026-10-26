## 变更内容 / What

<!-- 这个 PR 做了什么，为什么 -->

## 验证 / How it was tested

- [ ] `ruff check .` 和 `ruff format --check .` 通过
- [ ] `mypy` 通过
- [ ] `pytest -q --cov=bgm_audit` 通过；修复 bug 时附带了回归测试
- [ ] 如修改审核规则，已同步 README 规则表和 `tests/test_rules.py`
- [ ] 面向用户的变化已记录在 `CHANGELOG.md` 的 `[Unreleased]`

## 检查 / Checklist

- [ ] 默认流程仍然本地、离线，没有引入付费服务或 API Key
- [ ] 没有提交真实音乐、视频、`data/` 内容或个人信息
