# DUET Backend - OpenSCAD 升級版本
FROM ubuntu:24.04

# 避免互動式提示
ENV DEBIAN_FRONTEND=noninteractive

# 安裝基本工具
RUN apt-get update && apt-get install -y \
    software-properties-common \
    wget \
    xvfb \
    python3 \
    python3-pip \
    && rm -rf /var/lib/apt/lists/*

# ⚠️ 升級 OpenSCAD 到最新版本
# 方法 1：使用 snapshots PPA（推薦）
RUN add-apt-repository ppa:openscad/releases -y && \
    apt-get update && \
    apt-get install -y openscad && \
    rm -rf /var/lib/apt/lists/*

# 驗證 OpenSCAD 版本
RUN openscad --version

# 設定工作目錄
WORKDIR /app

# 複製 requirements.txt
COPY requirements.txt .

# 安裝 Python 依賴
RUN pip3 install --no-cache-dir -r requirements.txt

# 複製應用程式碼
COPY . .

# 設定環境變數
ENV DISPLAY=:99
ENV PYTHONUNBUFFERED=1

# 啟動 Xvfb 和應用
CMD Xvfb :99 -screen 0 1024x768x24 > /dev/null 2>&1 & \
    gunicorn --bind 0.0.0.0:$PORT --workers 2 --timeout 180 app:app
