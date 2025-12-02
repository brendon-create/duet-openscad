def generate_scad_script(letter1, letter2, font1, font2, size, pendant_x, pendant_y, pendant_z, pendant_rotation_y):
    """
    生成 DUET 雙字母 90度相交的 OpenSCAD 腳本
    
    參數:
    - letter1: 第一個字母 (正面)
    - letter2: 第二個字母 (側面, 旋轉90度)
    - font1, font2: 字體名稱
    - size: 目標高度 (mm)
    - pendant_x, pendant_y, pendant_z: 墜頭位置微調
    - pendant_rotation_y: 墜頭 Y 軸旋轉角度
    """
    
    # 動態深度 - 根據尺寸調整
    depth = size * 2.0
    
    # 動態精度 - 小尺寸可以用稍高精度
    if size <= 20:
        fn = 20  # 小吊飾 - 稍高精度
    else:
        fn = 16  # 大吊飾 - 低精度
    
    scad_script = f'''
// DUET 雙字母吊飾生成器 (90度相交版本)
// 使用 CSG intersection 確保無破面 (manifold)

$fn = {fn}; // 動態解析度 (根據尺寸優化)

// === 參數設定 ===
letter1 = "{letter1}";
letter2 = "{letter2}";
font1 = "{font1}";
font2 = "{font2}";
target_height = {size};      // 目標高度
depth = {depth};             // 深度 (高度的 2 倍)

// 墜頭參數
pendant_x = {pendant_x};
pendant_y = {pendant_y};
pendant_z = {pendant_z};
pendant_rotation_y = {pendant_rotation_y};

// 墜頭尺寸 (相對於 size)
pendant_outer_d = target_height * 0.15 * 2;  // 外徑
pendant_tube_d = target_height * 0.03 * 2;   // 管徑

// === 模組定義 ===

// 字母 1 模組 (正面, 超厚 extrude)
module letter1_shape() {{
    // 使用超大深度的 linear_extrude
    linear_extrude(height = depth, center = true)
        text(letter1, 
             size = target_height, 
             font = font1, 
             halign = "center", 
             valign = "center");
}}

// 字母 2 模組 (側面, 超厚 extrude + 旋轉 90度)
module letter2_shape() {{
    rotate([0, 90, 0])  // 繞 Y 軸旋轉 90度
        linear_extrude(height = depth, center = true)
            text(letter2, 
                 size = target_height, 
                 font = font2, 
                 halign = "center", 
                 valign = "center");
}}

// 墜頭模組 (簡化版 - 直接用 torus)
module pendant() {{
    rotate([0, 90, 0])  // 讓環口朝前
        rotate_extrude($fn = 12)  // 墜頭用更低解析度
            translate([pendant_outer_d / 2, 0, 0])
                circle(d = pendant_tube_d, $fn = 8);  // 圓管也降低
}}

// === 主組件 ===

// 整個模型旋轉 90 度,讓 Z 軸成為高度軸
rotate([90, 0, 0]) {{
    // 1. 雙字母交集 (核心邏輯!)
    intersection() {{
        letter1_shape();
        letter2_shape();
    }}

    // 2. 墜頭 (放在頂部,支援旋轉)
    translate([pendant_x, pendant_y, target_height / 2 + pendant_outer_d / 2 + pendant_z])
        rotate([0, pendant_rotation_y, 0])
            pendant();
}}
'''
    
    return scad_script

