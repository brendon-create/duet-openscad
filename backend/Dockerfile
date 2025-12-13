# 使用 Ubuntu 基礎映像
FROM ubuntu:22.04

# 避免互動式提示
ENV DEBIAN_FRONTEND=noninteractive

# 更新並安裝系統依賴
RUN apt-get update && apt-get install -y \
    python3 \
    python3-pip \
    openscad \
    xvfb \
    git \
    fontconfig \
    && rm -rf /var/lib/apt/lists/*

# 安裝 Google Fonts - 下載完整的 Google Fonts repository
RUN mkdir -p /usr/share/fonts/truetype/google-fonts && \
    git clone --filter=blob:none --sparse https://github.com/google/fonts.git /tmp/google-fonts && \
    cd /tmp/google-fonts && \
    git sparse-checkout set ofl && \
    find ofl -name "*.ttf" -exec cp {} /usr/share/fonts/truetype/google-fonts/ \; && \
    rm -rf /tmp/google-fonts && \
    fc-cache -f -v

# 設定工作目錄
WORKDIR /app

# 複製 requirements.txt
COPY requirements.txt .

# 安裝 Python 依賴
RUN pip3 install --no-cache-dir -r requirements.txt

# 複製應用程式碼
COPY . .

# 暴露端口
EXPOSE 5000

# 啟動 xvfb 並使用 gunicorn
# timeout 設定為 300 秒 (5 分鐘) 以支援高精度 STL 生成
CMD Xvfb :99 -screen 0 1024x768x24 > /dev/null 2>&1 & \
    gunicorn --bind 0.0.0.0:5000 --workers 2 --timeout 300 app:app
