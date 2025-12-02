def generate_scad_script(text, font, size, height, pendant_x, pendant_y, pendant_z, pendant_rotation_y):
    """
    生成 OpenSCAD 腳本
    
    參數:
    - text: 文字內容
    - font: 字體名稱
    - size: 字體大小
    - height: 厚度
    - pendant_x, pendant_y, pendant_z: 墜頭位置
    - pendant_rotation_y: 墜頭 Y 軸旋轉角度
    """
    
    scad_script = f'''
// DUET 文字吊飾生成器
// 使用 CSG 確保無破面 (manifold)

$fn = 50; // 圓滑度

// === 參數設定 ===
text_content = "{text}";
font_name = "{font}";
text_size = {size};
text_height = {height};

// 墜頭參數
pendant_x = {pendant_x};
pendant_y = {pendant_y};
pendant_z = {pendant_z};
pendant_rotation_y = {pendant_rotation_y};

// 墜頭尺寸
pendant_outer_diameter = 3;
pendant_inner_diameter = 2;
pendant_thickness = 1;

// === 模組定義 ===

// 文字模組
module text_base() {{
    linear_extrude(height = text_height)
        text(text_content, 
             size = text_size, 
             font = font_name, 
             halign = "center", 
             valign = "center");
}}

// 墜頭模組 (CSG 確保無破面)
module pendant() {{
    difference() {{
        // 外圓柱
        cylinder(h = pendant_thickness, 
                 d = pendant_outer_diameter, 
                 center = false);
        
        // 內孔 (稍微偏移避免 Z-fighting)
        translate([0, 0, -0.01])
            cylinder(h = pendant_thickness + 0.02, 
                     d = pendant_inner_diameter, 
                     center = false);
    }}
}}

// === 主組件 ===
union() {{
    // 文字主體 (直立)
    rotate([90, 0, 0])
        translate([0, 0, -text_height/2])
            text_base();
    
    // 墜頭 (4 軸控制)
    translate([pendant_x, pendant_y, pendant_z])
        rotate([0, pendant_rotation_y, 0])
            pendant();
}}
'''
    
    return scad_script
