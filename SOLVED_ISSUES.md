# DUET 專案已解決問題日誌
**Project: DUET - AI-Driven Custom Jewelry Design Platform**  
**Last Updated: 2025-12-15**

---

## 📋 目錄
- [核心架構問題](#核心架構問題)
- [座標系統問題](#座標系統問題)
- [旋轉邏輯問題](#旋轉邏輯問題)
- [參數傳遞問題](#參數傳遞問題)
- [字體系統問題](#字體系統問題)
- [部署問題](#部署問題)

---

## 🔒 核心架構問題

### ISSUE-001: 前後端分離架構確立
**日期**: 2025-12-14  
**狀態**: ✅ 已解決，**不應修改**

**問題描述**:
- 前端使用 Three.js + three-bvh-csg 進行快速預覽
- 後端使用 OpenSCAD 生成生產級 STL

**解決方案**:
- 前端：瀏覽器即時渲染，允許微小的視覺瑕疵
- 後端：雲端運算，生成 100% manifold 的 STL

**涉及檔案**:
- `duet-frontend-final.html` (前端渲染邏輯)
- `backend/app.py` (後端 API)
- `backend/scad_generator.py` (OpenSCAD 腳本生成)

**關鍵程式碼區域 - 不要修改**:
```
前端：generateModel() 函數
後端：generate_stl() 路由
```

**測試驗證**:
- ✅ 前端預覽流暢（<1秒）
- ✅ 後端 STL 無破面

---

## 🌐 座標系統問題

### ISSUE-002: Z-Up 座標系統對齊
**日期**: 2025-12-14  
**狀態**: ✅ 已解決，**不應修改**

**問題描述**:
- Three.js 預設 Y-up，需改為 Z-up
- OpenSCAD 預設 Z-up
- 必須確保前後端座標系統完全一致

**解決方案**:
```javascript
// 前端 - Three.js Z-up 設定
camera.up.set(0, 0, 1);  // Z 軸向上
camera.position.set(50, -70, 15);  // 45度角觀察
```

```python
# 後端 - OpenSCAD 使用原生 Z-up（不需特殊處理）
```

**涉及檔案**:
- `duet-frontend-final.html` (initScene 函數)

**關鍵程式碼 - 不要修改**:
```javascript
Line ~984-987: camera.up.set(0, 0, 1);
Line ~986: camera.position.set(50, -70, 15);
```

**測試驗證**:
- ✅ 前端 Z 軸指向上方
- ✅ 墜頭在模型頂部

---

## 🔄 旋轉邏輯問題

### ISSUE-003: Letter 旋轉邏輯對齊
**日期**: 2025-12-14 → 2025-12-15  
**狀態**: ✅ 已解決（經多次迭代），**不應修改**

**問題歷史**:
1. **第一版**: 使用局部軸旋轉（`.rotateX()`, `.rotateZ()`）
2. **第二版**: 改用全域軸旋轉（`rotateOnWorldAxis`）- **失敗**（Geometry 沒有此方法）
3. **第三版**: 使用旋轉矩陣（`applyMatrix4`）- ✅ **成功**

**最終解決方案**:

**前端** (duet-frontend-final.html):
```javascript
// Letter 1: XZ 平面
const rotationMatrix1 = new THREE.Matrix4();
rotationMatrix1.makeRotationX(Math.PI / 2);
geo1.applyMatrix4(rotationMatrix1);

// Letter 2: YZ 平面（先 X 後 Z）
const rotationMatrix2X = new THREE.Matrix4();
rotationMatrix2X.makeRotationX(Math.PI / 2);
geo2.applyMatrix4(rotationMatrix2X);

const rotationMatrix2Z = new THREE.Matrix4();
rotationMatrix2Z.makeRotationZ(Math.PI / 2);
geo2.applyMatrix4(rotationMatrix2Z);
```

**後端** (backend/scad_generator.py):
```python
# Letter 1: XZ 平面
module letter1_shape() {
    rotate([90, 0, 0])  # X 軸旋轉 90 度
        linear_extrude(...)
}

# Letter 2: YZ 平面（OpenSCAD 從內到外執行）
module letter2_shape() {
    rotate([0, 0, 90])      # 外層（後執行）
        rotate([90, 0, 0])  # 內層（先執行）
            linear_extrude(...)
}
```

**關鍵理解**:
- Three.js `applyMatrix4` 是**順序執行**（先 X 後 Z）
- OpenSCAD 嵌套 `rotate` 是**由內到外**（先內層後外層）
- 因此外層寫 Z，內層寫 X，才能匹配前端的「先 X 後 Z」

**涉及檔案**:
- `duet-frontend-final.html` (Line ~1105-1127)
- `backend/scad_generator.py` (Line ~49-60)

**關鍵程式碼 - 絕對不要修改**:
```
前端: generateModel() 中的旋轉矩陣邏輯
後端: letter1_shape() 和 letter2_shape() 的 rotate 順序
```

**測試驗證**:
- ✅ 前端兩字母垂直相交
- ✅ 後端 STL 與前端完全一致

---

## 📨 參數傳遞問題

### ISSUE-004: 前後端參數映射
**日期**: 2025-12-14  
**狀態**: ✅ 已解決，**不應修改**

**問題描述**:
- 前端發送扁平參數：`{bailX, bailY, bailZ, bailRotation}`
- 後端期望嵌套參數：`{pendant: {x, y, z, rotation_y}}`

**解決方案**:
後端同時支援兩種格式：

```python
# backend/app.py
if 'bailX' in data:
    # 扁平格式（前端發送）
    pendant_x = data.get('bailX', 0)
    pendant_y = data.get('bailY', 0)
    pendant_z = data.get('bailZ', 0)
    pendant_rotation = data.get('bailRotation', 0)
else:
    # 嵌套格式（舊版備用）
    pendant_config = data.get('pendant', {})
    pendant_x = pendant_config.get('x', 0)
    # ...
```

**座標軸映射**:
```python
pos_x = pendant_x                      # X 軸（左右）
pos_y = pendant_z                      # Y 軸（深度）- 注意！bailZ 對應 Y
pos_z = (size/2.0) + 2.0 + pendant_y  # Z 軸（高度）- bailY 對應 Z
```

**涉及檔案**:
- `backend/app.py` (generate_stl 函數)
- `backend/scad_generator.py` (參數處理)

**關鍵程式碼 - 不要修改**:
```
backend/app.py Line ~165-181: 參數解析邏輯
backend/scad_generator.py Line ~23-26: 座標映射
```

**測試驗證**:
- ✅ 墜頭位置與前端一致
- ✅ 墜頭旋轉角度正確

---

## 🔤 字體系統問題

### ISSUE-005: Google Fonts 安裝
**日期**: 2025-12-14  
**狀態**: ✅ 已解決，**不應修改**

**問題描述**:
- Docker 容器中字體安裝不完整
- 使用 sparse-checkout 導致部分字體遺失

**解決方案**:
完整克隆 Google Fonts repository：

```dockerfile
# backend/Dockerfile
RUN mkdir -p /usr/share/fonts/truetype/google-fonts && \
    cd /tmp && \
    git clone https://github.com/google/fonts.git && \
    cd fonts/ofl && \
    find . -name "*.ttf" -exec cp {} /usr/share/fonts/truetype/google-fonts/ \; && \
    cd /tmp && \
    rm -rf fonts && \
    fc-cache -f -v
```

**涉及檔案**:
- `backend/Dockerfile` (Line ~17-24)

**關鍵程式碼 - 不要修改**:
```
完整的 git clone 命令（不使用 sparse-checkout）
```

**測試驗證**:
```bash
curl https://duet-backend-wlw8.onrender.com/list-fonts | grep -i "chewy\|unica"
```
- ✅ Chewy 存在
- ✅ Unica One 存在
- ✅ BioRhyme Expanded 存在

---

### ISSUE-006: 字體驗證與白名單系統
**日期**: 2025-12-15  
**狀態**: 🚧 **進行中**（有 bug 待修正）

**問題描述**:
- 前端顯示的字體可能後端不支援
- 導致 STL 使用錯誤字體
- 客戶收到的產品與預覽不一致

**解決方案架構**:
1. **後端提供可用字體 API**: `/list-fonts`
2. **前端過濾字體清單**: 只顯示後端確認可用的
3. **後端嚴格驗證**: 不存在則拒絕生成

**當前狀態**:
- ⚠️ `/list-fonts` API 有 bug（返回 0 種字體）
- ⚠️ 需要修正 `fc-list` 命令參數

**涉及檔案**:
- `backend/app.py` (list_fonts, get_available_fonts, validate_font)
- `duet-frontend-final.html` (initAvailableFonts, initFontSelector)

**待修正**:
```python
# 正確的 fc-list 命令
['fc-list', ':family']  # ← 注意沒有空格
```

**測試驗證**:
- ⏳ 待修正後測試
- 目標：前端只顯示後端可用字體

---

## 🚀 部署問題

### ISSUE-007: Render 自動部署配置
**日期**: 2025-12-14  
**狀態**: ✅ 已解決

**問題描述**:
- Git push 後 Render 不會自動部署
- 需要手動觸發部署

**解決方案**:
- Render Dashboard → Settings → Auto-Deploy: "On Commit" ✅
- 或使用 `git commit --allow-empty` 強制觸發

**涉及檔案**:
- Render 平台設定（非程式碼）

**部署流程**:
```bash
git add <files>
git commit -m "message"
git push
# 等待 2-3 分鐘自動部署
```

**測試驗證**:
- ✅ Push 後自動觸發部署
- ✅ 部署完成後服務正常

---

### ISSUE-008: Render 冷啟動問題
**日期**: 2025-12-14  
**狀態**: ✅ 已規劃解決方案

**問題描述**:
- 免費方案 15 分鐘無請求後服務休眠
- 首次請求需等待 30-60 秒

**解決方案**:
- Keep-Alive Ping（前端定期請求 `/health`）
- 或升級付費方案

**狀態**:
- 🔄 尚未實作（非緊急）

---

## 🎨 前端渲染問題

### ISSUE-009: 初始金球顯示
**日期**: 2025-12-14  
**狀態**: ✅ 已解決，**功能正常**

**問題描述**:
- 頁面載入時顯示金色球體作為佔位符
- 選擇字母字體後才生成實際模型

**解決方案**:
這是**設計特性**，不是 bug：

```javascript
function showInitialSphere() {
    const geometry = new THREE.SphereGeometry(7.5, 64, 64);
    const material = getMaterial('gold18k', 'glossy');
    mainMesh = new THREE.Mesh(geometry, material);
    scene.add(mainMesh);
}
```

**涉及檔案**:
- `duet-frontend-final.html` (showInitialSphere 函數)

**關鍵邏輯 - 不要移除**:
```
初始球體 → 用戶選擇 → generateModel() → 替換為字母模型
```

---

## 📝 Git Workflow 規範

### 標準提交格式
```bash
git add <files>
git commit -m "[ISSUE-XXX] 簡短描述"
git push
```

### Commit Message 規範
```
[ISSUE-XXX] 標題

- 問題：...
- 解決：...
- 檔案：...
- 測試：...
```

---

## ⚠️ 禁止修改清單

**以下程式碼區域已確認正確，禁止修改**:

### 前端 (duet-frontend-final.html)
- ❌ `camera.up.set(0, 0, 1)` - Z-up 設定
- ❌ `camera.position.set(50, -70, 15)` - 相機位置
- ❌ Letter 旋轉矩陣邏輯 (Line ~1105-1127)
- ❌ `showInitialSphere()` - 初始球體
- ❌ Checkout 參數格式 (`bailX`, `bailY`, `bailZ`, `bailRotation`)

### 後端 (backend/app.py)
- ❌ 參數解析邏輯（扁平格式支援）
- ❌ `/health` endpoint

### 後端 (backend/scad_generator.py)
- ❌ `letter1_shape()` 旋轉：`rotate([90, 0, 0])`
- ❌ `letter2_shape()` 旋轉：外層 `[0,0,90]` 內層 `[90,0,0]`
- ❌ 座標映射：`pos_y = pendant_z`, `pos_z = ... + pendant_y`

### 後端 (backend/Dockerfile)
- ❌ Google Fonts 安裝（完整 clone）

---

## 📊 問題統計

- **已解決**: 8 個
- **進行中**: 1 個（字體驗證系統）
- **規劃中**: 1 個（Keep-Alive）
- **總計**: 10 個

---

## 🔄 更新記錄

| 日期 | 更新內容 | 更新者 |
|------|---------|--------|
| 2025-12-15 | 初始創建，記錄 ISSUE-001 至 ISSUE-009 | Claude |
| 2025-12-15 | 新增 ISSUE-006 字體驗證系統（進行中）| Claude |

---

## 📞 參考資料

- Render 部署 URL: https://duet-backend-wlw8.onrender.com
- GitHub Repo: brendon-create/duet-openscad
- Frontend 本地測試: 直接打開 duet-frontend-final.html

---

**最後更新**: 2025-12-15 13:00 UTC
