#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
with_shazam=0
if [[ "${1:-}" == "--with-shazam" ]]; then with_shazam=1; fi
echo "操作系统：$(uname -s)。安装 Python 3.12 本地环境。"
if command -v uv >/dev/null 2>&1; then
  uv python install 3.12
  uv venv --python 3.12 .venv --allow-existing
  installer=(uv pip install --python .venv/bin/python)
else
  if ! command -v python3.12 >/dev/null 2>&1; then
    echo "请先安装 Python 3.12 或 uv：https://docs.astral.sh/uv/getting-started/installation/"
    exit 1
  fi
  python3.12 -m venv .venv
  .venv/bin/python -m pip install --upgrade pip
  installer=(.venv/bin/python -m pip install)
fi
if ! command -v ffmpeg >/dev/null 2>&1 || ! command -v ffprobe >/dev/null 2>&1; then
  case "$(uname -s)" in
    Darwin)
      if command -v brew >/dev/null 2>&1; then brew install ffmpeg
      else echo "请先安装 Homebrew，然后运行 brew install ffmpeg"; exit 1; fi ;;
    Linux)
      elevated=()
      if [[ "$EUID" -ne 0 ]]; then elevated=(sudo); fi
      if command -v apt-get >/dev/null 2>&1; then
        "${elevated[@]}" apt-get update
        "${elevated[@]}" apt-get install -y ffmpeg
      elif command -v dnf >/dev/null 2>&1; then
        "${elevated[@]}" dnf install -y ffmpeg
      elif command -v pacman >/dev/null 2>&1; then
        "${elevated[@]}" pacman -S --needed --noconfirm ffmpeg
      else echo "请使用系统包管理器安装 FFmpeg（含 ffprobe），然后重试。"; exit 1; fi ;;
    *) echo "此脚本支持 macOS / Linux；Windows 请使用 install.bat"; exit 1 ;;
  esac
fi
requirements=requirements.txt
if [[ "$with_shazam" == 1 ]]; then requirements=requirements-shazam.txt; fi
"${installer[@]}" -r "$requirements"
.venv/bin/python scripts/check_environment.py
echo "安装完成。运行 ./start.sh，然后打开 http://127.0.0.1:8501"
