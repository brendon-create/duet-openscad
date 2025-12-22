def generate_scad_script(letter1, letter2, font1, font2, size, 
                        bailRelativeX, bailRelativeY, bailRelativeZ, bailRotation,
                        bailAbsoluteX, bailAbsoluteY, bailAbsoluteZ,
                        letter1Width, letter1Height, letter1Depth,
                        letter1OffsetX, letter1OffsetY, letter1OffsetZ,
                        letter2Width, letter2Height, letter2Depth,
                        letter2OffsetX, letter2OffsetY, letter2OffsetZ):
    """
    使用絕對尺寸同步法 (Absolute BBox Sync)
    
    關鍵修正：
    1. 前端傳遞精確的 BBox 尺寸和偏移量
    2. 後端使用 resize() 強制達到相同的絕對尺寸
    3. 使用 translate() 模擬 geo.center() 的效果
    """
    
    if size <= 20:
        fn = 64
    elif size <= 25:
        fn = 56
    else:
        fn = 48
    
    depth = size * 5.0
    bail_radius = 1.85  # innerRadius + tubeRadius = 1.5 + 0.35
    bail_tube = 0.35    # 管半徑 0.35mm，直徑 0.7mm
    
    import logging
    logger = logging.getLogger(__name__)
    logger.info(f"🔧 收到相對向量: X={bailRelativeX}, Y={bailRelativeY}, Z={bailRelativeZ}, Rotation={bailRotation}")
    logger.info(f"🔧 收到絕對座標: X={bailAbsoluteX}, Y={bailAbsoluteY}, Z={bailAbsoluteZ}")
    logger.info(f"📐 Letter1 BBox: W={letter1Width}, H={letter1Height}, D={letter1Depth}")
    logger.info(f"📐 Letter1 Offset: X={letter1OffsetX}, Y={letter1OffsetY}, Z={letter1OffsetZ}")
    logger.info(f"📐 Letter2 BBox: W={letter2Width}, H={letter2Height}, D={letter2Depth}")
    logger.info(f"📐 Letter2 Offset: X={letter2OffsetX}, Y={letter2OffsetY}, Z={letter2OffsetZ}")
    
    # 使用絕對座標定位墜頭
    pos_x = bailAbsoluteX
    pos_y = bailAbsoluteY
    pos_z = bailAbsoluteZ
    # 前端墜頭有初始 90° 旋轉
    bail_rotation_deg = bailRotation + 90
    
    scad_script = f'''// DUET Absolute BBox Sync System
$fn = {fn};

letter1 = "{letter1}";
letter2 = "{letter2}";
font1 = "{font1}";
font2 = "{font2}";
target_height = {size};
depth = {depth};

// Letter 1 BBox (前端測量的絕對尺寸)
letter1_width = {letter1Width};
letter1_height = {letter1Height};
letter1_depth = {letter1Depth};
letter1_offset_x = {letter1OffsetX};
letter1_offset_y = {letter1OffsetY};
letter1_offset_z = {letter1OffsetZ};

// Letter 2 BBox
letter2_width = {letter2Width};
letter2_height = {letter2Height};
letter2_depth = {letter2Depth};
letter2_offset_x = {letter2OffsetX};
letter2_offset_y = {letter2OffsetY};
letter2_offset_z = {letter2OffsetZ};

// 墜頭
bail_radius = {bail_radius};
bail_tube = {bail_tube};
pos_x = {pos_x};
pos_y = {pos_y};
pos_z = {pos_z};
bail_rotation = {bail_rotation_deg};

module letter1_shape() {{
    rotate([90, 0, 0])
        linear_extrude(height=depth, center=true)
            resize([letter1_width, letter1_height, 0], auto=false)  // 強制絕對尺寸
                translate([-letter1_offset_x, -letter1_offset_y, 0])  // 模擬 center()
                    text(letter1, font=font1, size=10, halign="left", valign="bottom");
}}

module letter2_shape() {{
    rotate([0, 0, 90])  // 外層（後執行）：Z 軸旋轉
        rotate([90, 0, 0])  // 內層（先執行）：X 軸旋轉
            linear_extrude(height=depth, center=true)
                resize([letter2_width, letter2_height, 0], auto=false)  // 強制絕對尺寸
                    translate([-letter2_offset_x, -letter2_offset_y, 0])  // 模擬 center()
                        text(letter2, font=font2, size=10, halign="left", valign="bottom");
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
    # Debug: 輸出生成的 SCAD 內容（前 50 行）
    logger.info("📄 Generated SCAD content (first 50 lines):")
    lines = scad_script.split('\n')
    for i, line in enumerate(lines[:50], 1):
        logger.info(f"  {i:3}: {line}")
    return scad_script
