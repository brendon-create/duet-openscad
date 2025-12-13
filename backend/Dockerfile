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
    wget \
    unzip \
    fontconfig \
    && rm -rf /var/lib/apt/lists/*

# 安裝 Google Fonts
RUN mkdir -p /usr/share/fonts/truetype/google-fonts && \
    cd /tmp && \
    # 下載常用 Google Fonts (可以根據需求增減)
    wget -q https://github.com/google/fonts/raw/main/ofl/roboto/Roboto-Regular.ttf -O /usr/share/fonts/truetype/google-fonts/Roboto-Regular.ttf && \
    wget -q https://github.com/google/fonts/raw/main/ofl/roboto/Roboto-Bold.ttf -O /usr/share/fonts/truetype/google-fonts/Roboto-Bold.ttf && \
    wget -q https://github.com/google/fonts/raw/main/ofl/opensans/OpenSans-Regular.ttf -O /usr/share/fonts/truetype/google-fonts/OpenSans-Regular.ttf && \
    wget -q https://github.com/google/fonts/raw/main/ofl/opensans/OpenSans-Bold.ttf -O /usr/share/fonts/truetype/google-fonts/OpenSans-Bold.ttf && \
    wget -q https://github.com/google/fonts/raw/main/ofl/playfairdisplay/PlayfairDisplay-Regular.ttf -O /usr/share/fonts/truetype/google-fonts/PlayfairDisplay-Regular.ttf && \
    wget -q https://github.com/google/fonts/raw/main/ofl/playfairdisplay/PlayfairDisplay-Bold.ttf -O /usr/share/fonts/truetype/google-fonts/PlayfairDisplay-Bold.ttf && \
    wget -q https://github.com/google/fonts/raw/main/ofl/montserrat/Montserrat-Regular.ttf -O /usr/share/fonts/truetype/google-fonts/Montserrat-Regular.ttf && \
    wget -q https://github.com/google/fonts/raw/main/ofl/montserrat/Montserrat-Bold.ttf -O /usr/share/fonts/truetype/google-fonts/Montserrat-Bold.ttf && \
    wget -q https://github.com/google/fonts/raw/main/ofl/lato/Lato-Regular.ttf -O /usr/share/fonts/truetype/google-fonts/Lato-Regular.ttf && \
    wget -q https://github.com/google/fonts/raw/main/ofl/lato/Lato-Bold.ttf -O /usr/share/fonts/truetype/google-fonts/Lato-Bold.ttf && \
    # 更新字體快取
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
