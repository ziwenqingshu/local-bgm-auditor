# 第三方组件 / Third-party notices

本项目自身代码采用 MIT 许可证（见 `LICENSE`）；各第三方组件保留各自的许可证。第三方源码中的版权头、许可证和 NOTICE 优先于本摘要。

## 随仓库分发的源码

| 组件 | 位置 | 许可证 | 说明 |
| --- | --- | --- | --- |
| [audfprint](https://github.com/dpwe/audfprint) | `vendor/audfprint/` | MIT，© 2014-5 Dan Ellis, Columbia University, and Google | 固定上游提交 `cb03ba99feafd41b8874307f0f4e808a6ce34362`，文件与上游逐字节一致、未修改算法；包含上游 `LICENSE`。上游仓库 `tests/` 中的商业音乐测试样本**未**随附。 |

## 运行依赖（通过 pip 安装，不随仓库分发）

| 组件 | 版本 | 许可证 |
| --- | --- | --- |
| [Streamlit](https://github.com/streamlit/streamlit) | 1.66.1 | Apache-2.0 |
| [NumPy](https://numpy.org/) | 1.26.4 | BSD-3-Clause |
| [SciPy](https://scipy.org/) | 1.17.1 | BSD-3-Clause |
| [pandas](https://pandas.pydata.org/) | 2.3.3 | BSD-3-Clause |
| [PyArrow](https://arrow.apache.org/) | 20.0.0 | Apache-2.0 |
| [psutil](https://github.com/giampaolo/psutil) | 7.2.2 | BSD-3-Clause |
| [filelock](https://github.com/tox-dev/filelock) | 3.32.7 | MIT |
| SQLite（随 Python 提供） | — | Public domain |

Streamlit 的传递依赖（如 Altair、Pillow、protobuf、Tornado 等）均为宽松许可证（BSD / MIT / Apache-2.0 / HPND 等），由 pip 安装时各自附带许可证文本。

## 可选依赖（默认不安装）

| 组件 | 版本 | 许可证 | 说明 |
| --- | --- | --- | --- |
| [ShazamIO](https://github.com/shazamio/ShazamIO) | 0.9.0 | MIT | 客户端开源；它调用的 Shazam 服务**不是**开源服务，并受其自身条款约束。严格开源 / 离线流程无需安装或启用。 |
| aiohttp（ShazamIO 的依赖） | — | Apache-2.0 AND MIT | |

## 开发依赖

pytest（MIT）、pytest-cov（MIT）、coverage（Apache-2.0）、ruff（MIT）、mypy（MIT）、pre-commit（MIT）、gitleaks（MIT，CI 中下载使用）。

## 外部程序

- **FFmpeg / ffprobe**：<https://ffmpeg.org/legal.html>，LGPL-2.1+ 或 GPL-2.0+，取决于发行包的编译选项。本项目只以子进程调用本机已安装的 FFmpeg，**不**重新分发其二进制。安装脚本使用系统包管理器（Homebrew / apt / dnf / pacman / winget）安装。
- **可选 Docker 镜像**：若你自行构建 `Dockerfile`，镜像会包含 Debian 软件源的 FFmpeg 及其依赖（GPL / LGPL 等）。分发该镜像时请遵守相应许可证。

## 音频素材

仓库、测试和一键演示中的所有音频都由 `bgm_audit/demo.py` 和 `tests/conftest.py` 以固定随机种子合成（正弦和弦 + 噪声打击声），为本项目原创，随项目以 MIT 许可证提供。仓库不包含任何第三方录音。

用户导入的参考音乐及其版权和授权材料由使用者自行提供并负责；软件许可证不会授予任何音乐作品的使用权。
