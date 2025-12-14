def generate_scad_script(letter1, letter2, font1, font2, size, pendant_x, pendant_y, pendant_z, pendant_rotation_y):
    """
    生成與前端 Z-Up 系統完全一致的 OpenSCAD 腳本
    
    關鍵修正（基於 Gemini 建議）：
    1. Letter 2 使用 rotate([90, 0, 90]) - 單一旋轉，不嵌套
    2. 參數映射：pendant_z → Y軸, pendant_y → Z軸
    3. 使用 resize() 確保精確高度
    4. union() 確保無破面
    """
    
    if size <= 20:
        fn = 64
    elif size <= 25:
        fn = 56
    else:
        fn = 48
    
    depth = size * 5.0
    bail_radius = size * 0.15
    bail_tube = size * 0.03
    
    # 墜頭位置（修正映射）
    pos_x = pendant_x
    pos_y = pendant_z  # 前端 bailZ → 後端 Y 軸（深度）
    pos_z = (size / 2.0) + 2.0 + pendant_y  # 前端 bailY → 後端 Z 軸（高度）
    
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
bail_rotation = {pendant_rotation_y};

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
    rotate([0, 0, 90])  // 第二步：繞 Z 軸轉 90 度
        rotate([90, 0, 0])  // 第一步：繞 X 軸轉 90 度
            linear_extrude(height=depth, center=true)
                letter_geometry(letter2, font2, target_height);
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
    return scad_script
