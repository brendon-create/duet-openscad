def generate_scad_script(letter1, letter2, font1, font2, size, bailRelativeX, bailRelativeY, bailRelativeZ, bailRotation):
    """
    生成與前端 Z-Up 系統完全一致的 OpenSCAD 腳本
    
    關鍵修正：
    1. Letter 2 旋轉順序匹配前端
    2. 使用相對向量定位墜頭：墜頭位置 = 主體中心 + 相對向量
    3. 使用 resize() 確保精確高度
    4. union() 確保無破面
    5. 字體名稱由後端嚴格驗證，直接使用
    """
    
    if size <= 20:
        fn = 64
    elif size <= 25:
        fn = 56
    else:
        fn = 48
    
    depth = size * 5.0
    bail_radius = 1.85
    bail_tube = 0.35
    
    import logging
    logger = logging.getLogger(__name__)
    logger.info(f"🔧 收到相對向量: X={bailRelativeX}, Y={bailRelativeY}, Z={bailRelativeZ}, Rotation={bailRotation}")
    
    # 墜頭位置 = 主體中心 + 相對向量
    # 在 OpenSCAD 中，主體使用 halign="center", valign="center"，所以中心點在原點 (0, 0, 0)
    pos_x = 0 + bailRelativeX
    pos_y = 0 + bailRelativeY
    pos_z = 0 + bailRelativeZ
    # 前端墜頭有初始 90° 旋轉（geometry.rotateZ(Math.PI/2)），後端需要加上這個偏移
    bail_rotation_deg = bailRotation + 90
    
    scad_script = f'''// DUET Z-Up System
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

module letter_geometry(char, font_name, target_h) {{
    // 先 extrude 成 3D，再 resize 整個 3D 物件
    rotate([90, 0, 0])
        resize([0, 0, target_h], auto=true)  // Z 軸是高度
            linear_extrude(height=depth, center=true)
                text(char, font=font_name, halign="center", valign="center");
}}

module letter1_shape() {{
    letter_geometry(letter1, font1, target_height);
}}

module letter2_shape() {{
    rotate([0, 0, 90])  // 外層（後執行）：Z 軸旋轉
        letter_geometry(letter2, font2, target_height);
}}

module bail() {{
    translate([pos_x, pos_y, pos_z])
        rotate([0, 0, bail_rotation])  // 用戶旋轉
            rotate([90, 0, 0])
                rotate_extrude(angle=360, $fn=32)
                    translate([bail_radius, 0, 0])
                        circle(r=bail_tube, $fn=24);
}}

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
