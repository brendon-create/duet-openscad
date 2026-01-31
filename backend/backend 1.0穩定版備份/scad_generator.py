def generate_scad_script(letter1, letter2, font1, font2, size, 
                        bailRelativeX, bailRelativeY, bailRelativeZ, bailRotation):
    """
    簡化備份版本 - 只使用 9 個參數
    
    改用這個版本的原因：
    1. BBox版本過於複雜，導致墜頭位置計算錯誤
    2. 使用 resize([0, 0, target_height], auto=true) 配合 halign/valign="center" 更簡單穩定
    3. intersection 的中心自然在原點 (0, 0, 0)
    4. 墜頭位置計算直接用 relative 向量，不需要複雜的絕對座標轉換
    
    參數:
        letter1, letter2: 字母
        font1, font2: 字體名稱
        size: 目標高度 (mm)
        bailRelativeX, bailRelativeY, bailRelativeZ: 墜頭相對位置向量
        bailRotation: 墜頭旋轉角度 (degrees)
    """
    
    # 動態精度設定
    if size <= 20:
        fn = 64      # 小尺寸 - 最高精度
    elif size <= 25:
        fn = 56      # 中尺寸 - 高精度
    else:
        fn = 48      # 大尺寸 - 較高精度
    
    depth = size * 5.0  # 確保完全交集
    
    # 墜頭參數（與前端一致）
    bail_radius = 1.85  # innerRadius(1.5) + tubeRadius(0.35)
    bail_tube = 0.35    # 管半徑 0.35mm，直徑 0.7mm
    
    # 使用相對向量計算墜頭位置
    pos_x = bailRelativeX
    pos_y = bailRelativeY
    pos_z = bailRelativeZ
    
    # 前端墜頭有初始 90° 偏移
    bail_rotation_deg = bailRotation + 90
    
    import logging
    logger = logging.getLogger(__name__)
    logger.info(f"📐 目標高度: {size}mm, 深度: {depth}mm, $fn: {fn}")
    logger.info(f"📐 墜頭半徑: {bail_radius}mm, 管半徑: {bail_tube}mm")
    logger.info(f"📍 墜頭相對位置: X={pos_x}, Y={pos_y}, Z={pos_z}")
    logger.info(f"🔄 墜頭旋轉: {bail_rotation_deg}° (前端{bailRotation}° + 90°)")
    
    scad_script = f'''// DUET Z-Up 簡化穩定版
// 使用 resize + halign/valign="center" 確保中心在原點
$fn = {fn};

letter1 = "{letter1}";
letter2 = "{letter2}";
font1 = "{font1}";
font2 = "{font2}";
target_height = {size};
depth = {depth};
bail_radius = {bail_radius};
bail_tube = {bail_tube};
pos_x = {pos_x};
pos_y = {pos_y};
pos_z = {pos_z};
bail_rotation = {bail_rotation_deg};

// 字母幾何模組 - 使用 resize 自動調整到目標高度
module letter_geometry(char, font_name, target_h) {{
    resize([0, target_h, 0], auto=true)
        text(char, font=font_name, halign="center", valign="center");
}}

// Letter 1: 平行於 XZ 平面
module letter1_shape() {{
    rotate([90, 0, 0])
        linear_extrude(height=depth, center=true)
            letter_geometry(letter1, font1, target_height);
}}

// Letter 2: 平行於 YZ 平面（外層繞 Z 軸旋轉 90°）
module letter2_shape() {{
    rotate([0, 0, 90])
        rotate([90, 0, 0])
            linear_extrude(height=depth, center=true)
                letter_geometry(letter2, font2, target_height);
}}

// 墜頭：torus 環
module bail() {{
    translate([pos_x, pos_y, pos_z])
        rotate([0, 0, bail_rotation])
            rotate([90, 0, 0])
                rotate_extrude(angle=360, $fn=32)
                    translate([bail_radius, 0, 0])
                        circle(r=bail_tube, $fn=24);
}}

// 主組件：intersection + bail
union() {{
    intersection() {{
        letter1_shape();
        letter2_shape();
    }}
    bail();
}}
'''
    
    # Debug: 輸出生成的 SCAD 內容（前 50 行）
    logger.info("📄 Generated SCAD content (first 50 lines):")
    lines = scad_script.split('\n')
    for i, line in enumerate(lines[:50], 1):
        logger.info(f"  {i:3}: {line}")
    
    return scad_script
