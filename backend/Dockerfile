# 使用 Ubuntu 22.04 作為基礎鏡像（PPA 有支援）
FROM ubuntu:22.04

# 設定環境變數避免互動式安裝
ENV DEBIAN_FRONTEND=noninteractive

# 安裝基本工具和依賴
RUN apt-get update && \
    apt-get install -y \
    software-properties-common \
    python3 \
    python3-pip \
    curl \
    && rm -rf /var/lib/apt/lists/*

# 安裝最新版 OpenSCAD（從 PPA）
RUN add-apt-repository ppa:openscad/releases -y && \
    apt-get update && \
    apt-get install -y openscad && \
    rm -rf /var/lib/apt/lists/*

# 設定工作目錄
WORKDIR /app

# 複製 requirements.txt 並安裝 Python 依賴
COPY requirements.txt .
RUN pip3 install --no-cache-dir -r requirements.txt

# 複製應用程式代碼
COPY . .

# 暴露端口
EXPOSE 8001

# 啟動命令
CMD ["python3", "app.py"]
