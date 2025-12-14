def generate_scad_script(letter1, letter2, font1, font2, size, pendant_x, pendant_y, pendant_z, pendant_rotation_y):
    """
    生成 DUET 雙字母 90度相交的 OpenSCAD 腳本
    Z-up 座標系統：XY為水平面，Z軸向上
    
    參數:
    - letter1: 第一個字母 (正面，在XZ平面)
    - letter2: 第二個字母 (側面，在YZ平面，旋轉90度)
    - font1, font2: Google Font 名稱
    - size: 目標高度 (沿Z軸，mm)
    - pendant_x, pendant_y, pendant_z: 墜頭位置微調
    - pendant_rotation_y: 墜頭繞Z軸旋轉角度
    """
    
    # 動態精度
    if size <= 20:
        fn = 64
    elif size <= 25:
        fn = 56
    else:
        fn = 48
    
    # 深度是高度的 5 倍（確保兩個字母完全交集）
    depth = size * 5.0
    
    scad_script = f'''
// DUET 雙字母吊飾生成器
// Z-up 座標系統：XY 水平面，Z 軸向上

$fn = {fn};

// === 參數 ===
letter1 = "{letter1}";
letter2 = "{letter2}";
font1 = "{font1}";
font2 = "{font2}";
target_height = {size};  // Z軸高度
depth = {depth};         // 深度（高度的5倍）

pendant_x = {pendant_x};
pendant_y = {pendant_y};
pendant_z = {pendant_z};
pendant_rotation = {pendant_rotation_y};  // 繞Z軸旋轉

pendant_outer_d = target_height * 0.15 * 2;
pendant_tube_d = target_height * 0.03 * 2;

// === 模組 ===

// 字母 1：在 XZ 平面（正面）
module letter1_shape() {{
    rotate([90, 0, 0])  // 將 text (XY平面) 轉到 XZ 平面
        linear_extrude(height = depth, center = true)
            text(letter1, 
                 size = target_height, 
                 font = font1, 
                 halign = "center", 
                 valign = "center");
}}

// 字母 2：在 YZ 平面（側面，垂直於字母1）
module letter2_shape() {{
    rotate([90, 0, 0])  // 先轉到 XZ 平面
        rotate([0, 0, 90])  // 再繞 Z 軸轉 90 度到 YZ 平面
            linear_extrude(height = depth, center = true)
                text(letter2, 
                     size = target_height, 
                     font = font2, 
                     halign = "center", 
                     valign = "center");
}}

// 墜頭：torus 環
module pendant() {{
    rotate([0, 90, 0])  // 調整環方向
        rotate_extrude($fn = 32)
            translate([pendant_outer_d / 2, 0, 0])
                circle(d = pendant_tube_d, $fn = 24);
}}

// === 主體 (Z-up: Z軸向上) ===

// 1. 雙字母交集
intersection() {{
    letter1_shape();
    letter2_shape();
}}

// 2. 墜頭（在 Z 軸頂部）
translate([pendant_x, pendant_y, target_height / 2 + pendant_outer_d / 2 + pendant_z])
    rotate([0, 0, pendant_rotation])  // 繞 Z 軸旋轉
        pendant();
'''
    
    return scad_script
