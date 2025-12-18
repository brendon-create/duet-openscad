def generate_scad_script(letter1, letter2, font1, font2, size, pendant_x, pendant_y, pendant_z, pendant_rotation_y):
    """
    生成與前端 Z-Up 系統完全一致的 OpenSCAD 腳本
    
    關鍵修正：
    1. Letter 2 旋轉順序匹配前端
    2. 參數映射：pendant_z → Y軸, pendant_y → Z軸
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
    
    # 墜頭規格 - 與前端一致
    # 目標：內徑 1.5mm, 管徑 0.7mm
    # OpenSCAD: translate([bail_radius, 0]) circle(r=bail_tube)
    # 內徑半徑 = bail_radius - bail_tube = 0.75mm
    # 因此：bail_tube = 0.35, bail_radius = 1.1
    bail_tube = 0.35      # 管半徑 (管徑 = 0.7mm)
    bail_radius = 1.1     # 到管中心的距離 (內徑 = 1.5mm)
    
    bail_rotation_with_offset = pendant_rotation_y + 90
    
    import logging
    logger = logging.getLogger(__name__)
    logger.info(f"🔧 DEBUG: pendant_rotation_y={pendant_rotation_y}, bail_rotation_with_offset={bail_rotation_with_offset}")
    
    # 墜頭位置
    pos_x = 0 + pendant_x
    pos_y = 0 + pendant_y
    pos_z = (size / 2.0) + 2.0 + pendant_z
    
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
bail_rotation = {bail_rotation_with_offset};

module letter_geometry(char, font_name, target_h) {{
    resize([0, target_h, 0], auto=true)
        text(char, font=font_name, halign="center", valign="center");
}}

module letter1_shape() {{
    rotate([90, 0, 0])
        linear_extrude(height=depth, center=true)
            letter_geometry(letter1, font1, target_height);
}}

module letter2_shape() {{
    rotate([0, 0, 90])  // 外層（後執行）：Z 軸旋轉
        rotate([90, 0, 0])  // 內層（先執行）：X 軸旋轉
            linear_extrude(height=depth, center=true)
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
