FROM python:3.9-slim

# 設置工作目錄
WORKDIR /app

# 安裝系統依賴
RUN apt-get update && apt-get install -y \
    openscad \
    fontconfig \
    git \
    wget \
    && rm -rf /var/lib/apt/lists/*

# 安裝 Google Fonts（完整clone，不使用 sparse-checkout）
RUN git clone https://github.com/google/fonts.git /usr/share/fonts/google-fonts \
    && fc-cache -f -v

# 複製應用文件
COPY requirements.txt .
COPY app.py .
COPY scad_generator.py .

# 安裝 Python 依賴
RUN pip install --no-cache-dir -r requirements.txt

# 設置環境變數
ENV PYTHONUNBUFFERED=1
ENV FLASK_APP=app.py

# 暴露端口
EXPOSE 5000

# 啟動命令（timeout 設為 300 秒，支持高精度模型）
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--workers", "2", "--timeout", "300", "app:app"]
