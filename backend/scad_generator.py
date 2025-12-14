def generate_scad_script(letter1, letter2, font1, font2, size, pendant_x, pendant_y, pendant_z, pendant_rotation_y):
    """
    生成 DUET 雙字母 90度相交的 OpenSCAD 腳本
    
    參數:
    - letter1: 第一個字母 (正面)
    - letter2: 第二個字母 (側面, 旋轉90度)
    - font1, font2: Google Font 名稱
    - size: 目標高度 (mm)
    - pendant_x, pendant_y, pendant_z: 墜頭位置微調
    - pendant_rotation_y: 墜頭 Z 軸旋轉角度
    """
    
    # 動態精度 - 根據尺寸平衡品質與速度
    if size <= 20:
        fn = 64      # 小尺寸 - 最高精度
    elif size <= 25:
        fn = 56      # 中尺寸 - 高精度
    else:
        fn = 48      # 大尺寸 - 較高精度
    
    # 深度必須非常大（高度的 5 倍）才能確保完全交集
    depth = size * 5.0
    
    scad_script = f'''
// DUET 雙字母吊飾生成器 (Z-up 座標系統)
// 優化參數以確保完美無破面 (manifold)

$fn = {fn}; // 高精度設定

// === 參數設定 ===
letter1 = "{letter1}";
letter2 = "{letter2}";
font1 = "{font1}";
font2 = "{font2}";
target_height = {size};      // 目標高度 (Z 軸)
depth = {depth};             // 深度 (高度的 5 倍,確保完全交集)

// 墜頭參數
pendant_x = {pendant_x};
pendant_y = {pendant_y};
pendant_z = {pendant_z};
pendant_rotation_y = {pendant_rotation_y};

// 墜頭尺寸 (相對於 size)
pendant_outer_d = target_height * 0.15 * 2;  // 外徑
pendant_tube_d = target_height * 0.03 * 2;   // 管徑

// === 模組定義 ===

// 字母 1 模組 (正面, 在 XZ 平面)
module letter1_shape() {{
    rotate([90, 0, 0])  // 將文字從 XY 平面轉到 XZ 平面
        linear_extrude(height = depth, center = true)
            text(letter1, 
                 size = target_height, 
                 font = font1, 
                 halign = "center", 
                 valign = "center");
}}

// 字母 2 模組 (側面, 在 YZ 平面, 垂直於字母1)
module letter2_shape() {{
    rotate([90, 0, 0])  // 先轉到 XZ 平面
        rotate([0, 0, 90])  // 再繞 Z 軸旋轉 90度到 YZ 平面
            linear_extrude(height = depth, center = true)
                text(letter2, 
                     size = target_height, 
                     font = font2, 
                     halign = "center", 
                     valign = "center");
}}

// 墜頭模組 (沿 Z 軸方向)
module pendant() {{
    rotate([90, 0, 0])  // 將環從 XY 平面轉到 XZ 平面
        rotate([0, 0, 90])  // 繞 Z 軸旋轉 90度
            rotate_extrude($fn = 32)
                translate([pendant_outer_d / 2, 0, 0])
                    circle(d = pendant_tube_d, $fn = 24);
}}

// === 主組件 (Z-up 座標系統) ===

// 1. 雙字母交集 (核心邏輯!)
intersection() {{
    letter1_shape();
    letter2_shape();
}}

// 2. 墜頭 (放在頂部, Z 軸正方向)
translate([pendant_x, pendant_y, target_height / 2 + pendant_outer_d / 2 + pendant_z])
    rotate([0, 0, pendant_rotation_y])  // 繞 Z 軸旋轉
        pendant();
'''
    
    return scad_script
