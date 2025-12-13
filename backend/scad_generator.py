def generate_scad_script(letter1, letter2, font1, font2, size, pendant_x, pendant_y, pendant_z, pendant_rotation_y):
    """
    生成 DUET 雙字母 90度相交的 OpenSCAD 腳本
    
    參數:
    - letter1: 第一個字母 (正面)
    - letter2: 第二個字母 (側面, 旋轉90度)
    - font1, font2: Google Font 名稱 (如 "Roboto", "Playfair Display")
    - size: 目標高度 (mm)
    - pendant_x, pendant_y, pendant_z: 墜頭位置微調
    - pendant_rotation_y: 墜頭 Y 軸旋轉角度
    """
    
    # 動態精度 - 根據尺寸平衡品質與速度
    if size <= 20:
        fn = 64      # 小尺寸 - 最高精度 (~120秒)
    elif size <= 25:
        fn = 56      # 中尺寸 - 高精度 (~150秒)
    else:
        fn = 48      # 大尺寸 - 較高精度 (~180秒)
    
    # 完整深度,確保字母完全交集
    depth = size * 5.0
    
    # OpenSCAD 使用已安裝的 Google Fonts
    # 前端傳來的字體名稱可以直接使用（如 "Roboto", "Open Sans"）
    scad_script = f'''
// DUET 雙字母吊飾生成器 (高精度生產版)
// 優化參數以確保完美無破面 (manifold)

$fn = {fn}; // 高精度設定

// === 參數設定 ===
letter1 = "{letter1}";
letter2 = "{letter2}";
font1 = "{font1}";
font2 = "{font2}";
target_height = {size};      // 目標高度
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

// 字母 1 模組 (正面, 朝向觀眾, extrude 沿 Y 軸方向)
module letter1_shape() {{
    rotate([90, 0, 0])  // 將文字從 XY 平面轉到 XZ 平面（正面）
        linear_extrude(height = depth, center = true)
            text(letter1, 
                 size = target_height, 
                 font = font1, 
                 halign = "center", 
                 valign = "center");
}}

// 字母 2 模組 (側面, 垂直於字母1, extrude 沿 X 軸方向)
module letter2_shape() {{
    rotate([0, 90, 0])  // 將文字旋轉到 YZ 平面（側面）
        rotate([90, 0, 0])  // 調整文字方向
            linear_extrude(height = depth, center = true)
                text(letter2, 
                     size = target_height, 
                     font = font2, 
                     halign = "center", 
                     valign = "center");
}}

// 墜頭模組 (高精度版, 沿 Z 軸方向)
module pendant() {{
    rotate([90, 0, 0])  // 將環從 XY 平面轉到 XZ 平面
        rotate([0, 0, 90])  // 再繞 Z 軸旋轉 90 度
            rotate_extrude($fn = 32)  // 墜頭高精度
                translate([pendant_outer_d / 2, 0, 0])
                    circle(d = pendant_tube_d, $fn = 24);  // 圓管高精度
}}

// === 主組件 (Z-up 座標系統) ===

// 1. 雙字母交集 (核心邏輯!)
intersection() {{
    letter1_shape();
    letter2_shape();
}}

// 2. 墜頭 (放在頂部, 支援旋轉)
translate([pendant_x, pendant_y, target_height / 2 + pendant_outer_d / 2 + pendant_z])
    rotate([0, 0, pendant_rotation_y])  // 繞 Z 軸旋轉
        pendant();
'''
    
    return scad_script
