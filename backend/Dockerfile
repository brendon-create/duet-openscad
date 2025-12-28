# 使用 Ubuntu 22.04 作為基礎鏡像
FROM ubuntu:22.04

# 設定環境變數避免互動式安裝
ENV DEBIAN_FRONTEND=noninteractive

# 安裝基本工具
RUN apt-get update && \
    apt-get install -y \
    curl \
    gnupg \
    ca-certificates \
    python3 \
    python3-pip \
    && rm -rf /var/lib/apt/lists/*

# 添加 OpenSCAD 源（OpenSUSE Build Service）
RUN echo "deb https://download.opensuse.org/repositories/home:/t-paul/xUbuntu_22.04/ ./" > /etc/apt/sources.list.d/openscad.list && \
    curl -fsSL https://download.opensuse.org/repositories/home:/t-paul/xUbuntu_22.04/Release.key | gpg --dearmor -o /etc/apt/trusted.gpg.d/openscad.gpg

# 安裝 OpenSCAD
RUN apt-get update && \
    apt-get install -y openscad && \
    rm -rf /var/lib/apt/lists/*

# 驗證 OpenSCAD 版本
RUN openscad --version

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
CMD ["python3",