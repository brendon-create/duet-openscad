import subprocess
import tempfile
import os
import numpy as np
from stl import mesh
import logging

logger = logging.getLogger(__name__)

def generate_scad_intersection_only(letter1, letter2, font1, font2, size):
    """第一階段：只生成交集，不含墜頭"""
    
    if size <= 20:
        fn = 64
    elif size <= 25:
        fn = 56
    else:
        fn = 48
    
    depth = size * 5.0
    
    scad_script = f'''// DUET - Stage 1: Intersection Only
$fn = {fn};

letter1 = "{letter1}";
letter2 = "{letter2}";
font1 = "{font1}";
font2 = "{font2}";
target_height = {size};
depth = {depth};

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
    rotate([0, 0, 90])
        rotate([90, 0, 0])
            linear_extrude(height=depth, center=true)
                letter_geometry(letter2, font2, target_height);
}}

// 只輸出交集
intersection() {{
    letter1_shape();
    letter2_shape();
}}
'''
    return scad_script


def calculate_stl_center(stl_path):
    """計算 STL 的 bounding box center"""
    try:
        stl_mesh = mesh.Mesh.from_file(stl_path)
        vertices = stl_mesh.vectors.reshape(-1, 3)
        
        bbox_min = vertices.min(axis=0)
        bbox_max = vertices.max(axis=0)
        center = (bbox_min + bbox_max) / 2
        
        logger.info(f"📏 Bounding box: min={bbox_min}, max={bbox_max}")
        logger.info(f"📍 Center: {center}")
        
        return center
    except Exception as e:
        logger.error(f"❌ 計算中心失敗: {e}")
        return np.array([0, 0, 0])


def generate_scad_final_with_bail(temp_stl_path, center, size, pendant_x, pendant_y, pendant_z, pendant_rotation_y):
    """第二階段：import 居中的模型 + 加墜頭"""
    
    bail_radius = 2.0
    bail_tube = 0.7
    bail_rotation_with_offset = pendant_rotation_y + 90
    
    # 墜頭位置（相對於居中後的原點）
    pos_x = pendant_x
    pos_y = pendant_y
    pos_z = (size / 2.0) + 2.0 + pendant_z
    
    # 居中偏移（反向）
    offset_x = -center[0]
    offset_y = -center[1]
    offset_z = -center[2]
    
    scad_script = f'''// DUET - Stage 2: Import + Center + Bail
$fn = 64;

pos_x = {pos_x};
pos_y = {pos_y};
pos_z = {pos_z};
bail_rotation = {bail_rotation_with_offset};
bail_radius = {bail_radius};
bail_tube = {bail_tube};

// 居中偏移
offset_x = {offset_x};
offset_y = {offset_y};
offset_z = {offset_z};

module centered_model() {{
    translate([offset_x, offset_y, offset_z])
        import("{temp_stl_path}");
}}

module bail() {{
    translate([pos_x, pos_y, pos_z])
        rotate([0, 0, bail_rotation])
            rotate([90, 0, 0])
                rotate_extrude(angle=360, $fn=32)
                    translate([bail_radius, 0, 0])
                        circle(r=bail_tube, $fn=24);
}}

// Union 確保無破面
union() {{
    centered_model();
    bail();
}}
'''
    return scad_script


def run_openscad(scad_script, output_stl_path):
    """執行 OpenSCAD 生成 STL"""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.scad', delete=False) as f:
        scad_path = f.name
        f.write(scad_script)
    
    try:
        logger.info(f"🔧 Running OpenSCAD: {scad_path} -> {output_stl_path}")
        
        result = subprocess.run(
            ['openscad', '-o', output_stl_path, scad_path],
            capture_output=True,
            text=True,
            timeout=120
        )
        
        if result.returncode != 0:
            logger.error(f"❌ OpenSCAD error: {result.stderr}")
            raise Exception(f"OpenSCAD failed: {result.stderr}")
        
        logger.info(f"✅ OpenSCAD success")
        return output_stl_path
        
    finally:
        os.unlink(scad_path)


def generate_stl_two_stage(letter1, letter2, font1, font2, size, pendant_x, pendant_y, pendant_z, pendant_rotation_y):
    """完整的兩階段生成流程"""
    
    logger.info("🚀 開始兩階段 STL 生成")
    
    # === 第一階段：生成交集 ===
    logger.info("📦 Stage 1: 生成交集...")
    scad_intersection = generate_scad_intersection_only(letter1, letter2, font1, font2, size)
    
    temp_stl_1 = tempfile.NamedTemporaryFile(suffix='.stl', delete=False).name
    run_openscad(scad_intersection, temp_stl_1)
    
    # === 計算中心 ===
    logger.info("📏 計算 bounding box center...")
    center = calculate_stl_center(temp_stl_1)
    
    # === 第二階段：居中 + 墜頭 ===
    logger.info("📦 Stage 2: 居中 + 墜頭...")
    scad_final = generate_scad_final_with_bail(
        temp_stl_1, center, size,
        pendant_x, pendant_y, pendant_z, pendant_rotation_y
    )
    
    final_stl = tempfile.NamedTemporaryFile(suffix='.stl', delete=False).name
    run_openscad(scad_final, final_stl)
    
    # === 讀取最終 STL ===
    with open(final_stl, 'rb') as f:
        stl_bytes = f.read()
    
    # === 清理臨時檔案 ===
    os.unlink(temp_stl_1)
    os.unlink(final_stl)
    
    logger.info("✅ 兩階段生成完成")
    return stl_bytes


# === 範例使用 ===
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    
    stl_data = generate_stl_two_stage(
        letter1="A",
        letter2="B",
        font1="Roboto",
        font2="Roboto",
        size=20,
        pendant_x=0,
        pendant_y=0,
        pendant_z=0,
        pendant_rotation_y=0
    )
    
    with open("test_output.stl", "wb") as f:
        f.write(stl_data)
    
    print("✅ 測試完成：test_output.stl")
