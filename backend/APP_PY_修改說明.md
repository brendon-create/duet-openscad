# app.py 修改說明

## 需要修改的地方

在 `/generate` endpoint 中，找到處理參數的部分，添加新的 BBox 參數：

```python
# 原有的墜頭參數
bailRelativeX = data.get('bailRelativeX', 0)
bailRelativeY = data.get('bailRelativeY', 0)
bailRelativeZ = data.get('bailRelativeZ', 0)
bailRotation = data.get('bailRotation', 0)

# **新增：Letter 1 BBox 參數**
letter1Width = data.get('letter1Width', 0)
letter1Height = data.get('letter1Height', 0)
letter1Depth = data.get('letter1Depth', 0)
letter1OffsetX = data.get('letter1OffsetX', 0)
letter1OffsetY = data.get('letter1OffsetY', 0)
letter1OffsetZ = data.get('letter1OffsetZ', 0)

# **新增：Letter 2 BBox 參數**
letter2Width = data.get('letter2Width', 0)
letter2Height = data.get('letter2Height', 0)
letter2Depth = data.get('letter2Depth', 0)
letter2OffsetX = data.get('letter2OffsetX', 0)
letter2OffsetY = data.get('letter2OffsetY', 0)
letter2OffsetZ = data.get('letter2OffsetZ', 0)
```

## 修改函數調用

找到調用 `generate_scad_script` 的地方，修改為：

```python
scad_content = generate_scad_script(
    letter1=letter1,
    letter2=letter2,
    font1=font1,
    font2=font2,
    size=size,
    bailRelativeX=bailRelativeX,
    bailRelativeY=bailRelativeY,
    bailRelativeZ=bailRelativeZ,
    bailRotation=bailRotation,
    # **新增的 BBox 參數**
    letter1Width=letter1Width,
    letter1Height=letter1Height,
    letter1Depth=letter1Depth,
    letter1OffsetX=letter1OffsetX,
    letter1OffsetY=letter1OffsetY,
    letter1OffsetZ=letter1OffsetZ,
    letter2Width=letter2Width,
    letter2Height=letter2Height,
    letter2Depth=letter2Depth,
    letter2OffsetX=letter2OffsetX,
    letter2OffsetY=letter2OffsetY,
    letter2OffsetZ=letter2OffsetZ
)
```

## 完成後

將 `scad_generator_bbox.py` 重新命名為 `scad_generator.py` 並上傳到 GitHub。
