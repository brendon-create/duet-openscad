def generate_scad_script(letter1, letter2, font1, font2, size, pendant_x, pendant_y, pendant_z, pendant_rotation_y):
    """
    生成 DUET 雙字母 90度相交的 OpenSCAD 腳本
    完全對應前端 Three.js 的 Z-up 座標系統
    
    參數:
    - letter1: 第一個字母 (正面)
    - letter2: 第二個字母 (側面, 旋轉90度)
    - font1, font2: Google Font 名稱
    - size: 目標高度 (mm)
    - pendant_x, pendant_y, pendant_z: 墜頭位置微調
    - pendant_rotation_y: 墜頭 Z 軸旋轉角度
    """
    
    # 動態精度
    if size <= 20:
        fn = 64
    elif size <= 25:
        fn = 56
    else:
        fn = 48
    
    # 深度是高度的 5 倍（確保完全交集）
    depth = size * 5.0
    
    scad_script = f'''
// DUET 雙字母吊飾生成器
// Z-up 座標系統（對應前端 Three.js）

$fn = {fn};

// === 參數 ===
letter1 = "{letter1}";
letter2 = "{letter2}";
font1 = "{font1}";
font2 = "{font2}";
target_height = {size};
depth = {depth};

pendant_x = {pendant_x};
pendant_y = {pendant_y};
pendant_z = {pendant_z};
pendant_rotation_z = {pendant_rotation_y};  // 注意：前端叫 rotation_y，但實際是繞Z軸

pendant_outer_d = target_height * 0.15 * 2;
pendant_tube_d = target_height * 0.03 * 2;

// === 模組 ===

// 字母 1：XY平面 → rotateX(-90) → XZ平面（Z向上）
module letter1_shape() {{
    rotate([-90, 0, 0])  // 對應前端 rotateX(-Math.PI/2)
        linear_extrude(height = depth, center = true)
            text(letter1, 
                 size = target_height, 
                 font = font1, 
                 halign = "center", 
                 valign = "center");
}}

// 字母 2：XY平面 → rotateX(-90) → XZ平面 → rotateZ(90) → YZ平面
module letter2_shape() {{
    rotate([-90, 0, 0])  // 對應前端 rotateX(-Math.PI/2)
        rotate([0, 0, 90])  // 對應前端 rotateZ(Math.PI/2)
            linear_extrude(height = depth, center = true)
                text(letter2, 
                     size = target_height, 
                     font = font2, 
                     halign = "center", 
                     valign = "center");
}}

// 墜頭：torus 環
module pendant() {{
    rotate([0, 90, 0])  // 讓環口朝向合適方向
        rotate_extrude($fn = 32)
            translate([pendant_outer_d / 2, 0, 0])
                circle(d = pendant_tube_d, $fn = 24);
}}

// === 主體 ===

// 1. 雙字母交集
intersection() {{
    letter1_shape();
    letter2_shape();
}}

// 2. 墜頭（在Z軸頂部）
translate([pendant_x, pendant_y, target_height / 2 + pendant_outer_d / 2 + pendant_z])
    rotate([0, 0, pendant_rotation_z])
        pendant();
'''
    
    return scad_script
