# 🎨 DUET - 文字吊飾生成器

使用 OpenSCAD 生成無破面 (manifold) 的 3D 列印 STL 檔案

## ✨ 特色

- ✅ **無破面保證** - 使用 CSG 建模確保 manifold
- ✅ **4 軸墜頭控制** - X, Y, Z, Rotation Y
- ✅ **直立座標系統** - 文字垂直於 XY 平面
- ✅ **雲端部署** - Render + Vercel 全自動
- ✅ **Keep-Alive** - 免費版不休眠

## 🏗️ 技術棧

- **後端**: Flask + OpenSCAD (Render)
- **前端**: HTML + Vanilla JS (Vercel)
- **版本控制**: GitHub

## 📁 專案結構

```
duet-openscad/
├── backend/
│   ├── app.py              # Flask API
│   ├── scad_generator.py   # OpenSCAD 腳本生成
│   ├── requirements.txt    # Python 依賴
│   └── Dockerfile          # 容器設定
└── frontend/
    └── index.html          # 使用者介面
```

## 🚀 部署步驟

### 1. GitHub 設置

```bash
git init
git add .
git commit -m "Initial commit"
git remote add origin https://github.com/YOUR_USERNAME/duet-openscad.git
git push -u origin main
```

### 2. Render 部署 (後端)

1. 前往 [Render Dashboard](https://dashboard.render.com/)
2. 點擊 "New" → "Web Service"
3. 連接 GitHub repo
4. 設定:
   - **Name**: duet-backend
   - **Root Directory**: `backend`
   - **Environment**: Docker
   - **Instance Type**: Free
5. 點擊 "Create Web Service"

### 3. Vercel 部署 (前端)

1. 前往 [Vercel Dashboard](https://vercel.com/dashboard)
2. 點擊 "New Project"
3. 連接 GitHub repo
4. 設定:
   - **Framework Preset**: Other
   - **Root Directory**: `frontend`
5. 點擊 "Deploy"

### 4. 連接前後端

1. 複製 Render 給的後端網址 (例如: `https://duet-backend.onrender.com`)
2. 在前端頁面的「後端 API 網址」欄位貼上

## 📝 API 端點

### GET /health
健康檢查

**回應:**
```json
{
  "status": "healthy",
  "openscad": "OpenSCAD version 2021.01",
  "temp_dir": "/tmp"
}
```

### POST /generate
生成 STL 檔案

**請求:**
```json
{
  "text": "DUET",
  "font": "Liberation Sans:style=Bold",
  "size": 10,
  "height": 2,
  "pendant": {
    "x": 0,
    "y": 0,
    "z": 0,
    "rotation_y": 0
  }
}
```

**回應:**
- 成功: STL 檔案 (binary)
- 失敗: JSON 錯誤訊息

## 🎛️ 墜頭參數說明

- **X 軸**: 水平移動 (-20 ~ 20 mm)
- **Y 軸**: 前後移動 (-20 ~ 20 mm)
- **Z 軸**: 上下移動 (-20 ~ 20 mm)
- **Rotation Y**: 繞 Y 軸旋轉 (-180° ~ 180°)

## 🔧 本地開發

### 後端

```bash
cd backend
pip install -r requirements.txt
python app.py
```

### 前端

直接開啟 `frontend/index.html` 或使用:

```bash
cd frontend
python -m http.server 8000
```

## 📄 授權

MIT License

## 🤝 貢獻

歡迎 Pull Requests!

---

Made with ❤️ by DUET Team
