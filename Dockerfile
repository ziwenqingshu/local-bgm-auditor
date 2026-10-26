# 可选的容器运行方式；推荐方式仍是 README 中的本地安装。
# docker build -t local-bgm-auditor .
# docker run --rm -p 127.0.0.1:8501:8501 -v "$PWD/data:/data" local-bgm-auditor
FROM python:3.12-slim-bookworm

RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    BGM_DATA_DIR=/data

WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY app.py ./
COPY bgm_audit ./bgm_audit
COPY vendor ./vendor
COPY scripts ./scripts
COPY .streamlit ./.streamlit

RUN useradd --create-home --uid 1000 auditor \
    && mkdir -p /data && chown auditor:auditor /data
USER auditor
VOLUME ["/data"]
EXPOSE 8501

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8501/_stcore/health')"

# 容器内需监听 0.0.0.0 才能被端口映射访问；请只把端口映射到宿主机的 127.0.0.1。
CMD ["python", "-m", "streamlit", "run", "app.py", "--server.address", "0.0.0.0", "--server.port", "8501", "--browser.gatherUsageStats", "false"]
