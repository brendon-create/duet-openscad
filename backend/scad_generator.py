def generate_scad_script(letter1, letter2, font1, font2, size, pendant_x, pendant_y, pendant_z, pendant_rotation_y):
    """
    生成 DUET 雙字母 90度相交的 OpenSCAD 腳本
    Z-up 座標系統：XY為水平面，Z軸向上
    
    正確的建模邏輯：
    - Letter 1: 在 XZ 平面，沿 Y 軸 extrude
    - Letter 2: 在 YZ 平面，沿 X 軸 extrude
    - 兩者天然垂直，取交集
    """
    
    # 動態精度
    if size <= 20:
        fn = 64
    elif size <= 25:
        fn = 56
    else:
        fn = 48
    
    # 深度是高度的 5 倍
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
depth = {depth};         // extrude 深度（高度的5倍）

pendant_x = {pendant_x};
pendant_y = {pendant_y};
pendant_z = {pendant_z};
pendant_rotation = {pendant_rotation_y};  // 繞Z軸旋轉

pendant_outer_d = target_height * 0.15 * 2;
pendant_tube_d = target_height * 0.03 * 2;

// === 模組 ===

// Letter 1: XZ 平面，沿 Y 軸 extrude
module letter1_shape() {{
    rotate([90, 0, 0])  // 將 extrude 後的立體從 XY-Z 轉到 XZ-Y
        linear_extrude(height = depth, center = true)
            text(letter1, 
                 size = target_height, 
                 font = font1, 
                 halign = "center", 
                 valign = "center");
}}

// Letter 2: YZ 平面，沿 X 軸 extrude
module letter2_shape() {{
    rotate([90, 0, 0])  // 先轉到 XZ 平面，extrude 沿 -Y
        rotate([0, 0, 90])  // 再繞 Z 軸轉 90度到 YZ 平面，extrude 沿 -X
            linear_extrude(height = depth, center = true)
                text(letter2, 
                     size = target_height, 
                     font = font2, 
                     halign = "center", 
                     valign = "center");
}}

// 墜頭：torus 環
module pendant() {{
    rotate([0, 90, 0])
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

// 2. 墜頭（在 Z 軸頂部）
translate([pendant_x, pendant_y, target_height / 2 + pendant_outer_d / 2 + pendant_z])
    rotate([0, 0, pendant_rotation])
        pendant();
'''
    
    return scad_script
