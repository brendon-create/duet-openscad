def generate_scad_script(letter1, letter2, font1, font2, size, bailRelativeX, bailRelativeY, bailRelativeZ, bailRotation):
    """
    生成與前端 Z-Up 系統完全一致的 OpenSCAD 腳本
    
    關鍵修正：
    1. 在 2D 階段使用 scale() 調整文字大小，而不是在 3D 物件上用 resize()
    2. 確保主物件和墜頭在同一比例尺下
    3. 統一旋轉邏輯與前端一致
    """
    
    if size <= 20:
        fn = 64
    elif size <= 25:
        fn = 56
    else:
        fn = 48
    
    # 深度保持為 size 的 5 倍
    depth = size * 5.0
    
    # 墜頭尺寸
    bail_radius = 1.85
    bail_tube = 0.35
    
    import logging
    logger = logging.getLogger(__name__)
    logger.info(f"🔧 收到參數: size={size}, bailRelativeX={bailRelativeX}, bailRelativeY={bailRelativeY}, bailRelativeZ={bailRelativeZ}, bailRotation={bailRotation}")
    
    # 墜頭位置 = 主體中心 + 相對向量
    pos_x = 0 + bailRelativeX
    pos_y = 0 + bailRelativeY
    pos_z = 0 + bailRelativeZ
    
    # 前端墜頭有初始 90° 旋轉
    bail_rotation_deg = bailRotation + 90
    
    # ✅ 關鍵修正：計算縮放比例，作用在 2D text 上
    # OpenSCAD text(size=10) 約等於 Three.js TextGeometry(size=15)
    # 因此需要縮放 size/10
    text_scale = size / 10.0
    
    scad_script = f'''// DUET Z-Up System - 修正版
$fn = {fn};

letter1 = "{letter1}";
letter2 = "{letter2}";
font1 = "{font1}";
font2 = "{font2}";
target_height = {size};
depth = {depth};
text_scale = {text_scale};
bail_radius = {bail_radius};
bail_tube = {bail_tube};
pos_x = {pos_x};
pos_y = {pos_y};
pos_z = {pos_z};
bail_rotation = {bail_rotation_deg};

module letter1_shape() {{
    rotate([90, 0, 0])
        linear_extrude(height=depth, center=true)
            scale([text_scale, text_scale, 1])  // ✅ 在 2D 階段縮放
                text(letter1, font=font1, size=10, halign="center", valign="center");
}}

module letter2_shape() {{
    rotate([0, 0, 90])
        rotate([90, 0, 0])
            linear_extrude(height=depth, center=true)
                scale([text_scale, text_scale, 1])  // ✅ 在 2D 階段縮放
                    text(letter2, font=font2, size=10, halign="center", valign="center");
}}

module bail() {{
    translate([pos_x, pos_y, pos_z])
        rotate([0, 0, bail_rotation])
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
    
    logger.info("📄 Generated SCAD content (first 50 lines):")
    lines = scad_script.split('\n')
    for i, line in enumerate(lines[:50], 1):
        logger.info(f"  {i:3}: {line}")
    
    return scad_script
