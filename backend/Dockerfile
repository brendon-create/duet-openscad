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
    && rm -rf /var/lib/apt/lists/*

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

# 使用 gunicorn 啟動
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--workers", "2", "--timeout", "60", "app:app"]
