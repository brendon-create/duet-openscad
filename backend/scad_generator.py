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
    logger.info("📄 Stage 1 SCAD generated (intersection only)")
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
        raise


def generate_scad_final_with_bail(temp_stl_path, center, relative_bail_x, relative_bail_y, relative_bail_z, pendant_rotation_y):
    """第二階段：import 居中的模型 + 加墜頭（使用相對位置）"""
    
    bail_radius = 2.0
    bail_tube = 0.7
    bail_rotation_with_offset = pendant_rotation_y + 90
    
    # ✅ 墜頭絕對位置 = 主體中心 + 相對位置
    pos_x = float(center[0]) + relative_bail_x
    pos_y = float(center[1]) + relative_bail_y
    pos_z = float(center[2]) + relative_bail_z
    
    # 居中偏移（反向）
    offset_x = -float(center[0])
    offset_y = -float(center[1])
    offset_z = -float(center[2])
    
    # 轉換 Windows 路徑為 OpenSCAD 格式（如果需要）
    import_path = temp_stl_path.replace('\\', '/')
    
    scad_script = f'''// DUET - Stage 2: Import + Center + Bail (相對位置模式)
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
        import("{import_path}");
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
    logger.info(f"📄 Stage 2 SCAD generated (import + bail)")
    logger.info(f"   Center offset: ({offset_x:.3f}, {offset_y:.3f}, {offset_z:.3f})")
    logger.info(f"   Bail position: ({pos_x}, {pos_y}, {pos_z})")
    return scad_script


def run_openscad(scad_script, output_stl_path, env=None):
    """執行 OpenSCAD 生成 STL"""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.scad', delete=False) as f:
        scad_path = f.name
        f.write(scad_script)
    
    try:
        logger.info(f"🔧 Running OpenSCAD: {scad_path} -> {output_stl_path}")
        
        cmd = [
            'openscad',
            '-o', output_stl_path,
            '--export-format', 'binstl',
            scad_path
        ]
        
        # 使用提供的環境變數或創建新的
        if env is None:
            env = os.environ.copy()
            env['DISPLAY'] = ':99'
        
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=180,
            env=env
        )
        
        if result.returncode != 0:
            logger.error(f"❌ OpenSCAD error: {result.stderr}")
            raise Exception(f"OpenSCAD failed: {result.stderr}")
        
        if not os.path.exists(output_stl_path):
            raise Exception("STL file not generated")
        
        logger.info(f"✅ OpenSCAD success: {output_stl_path}")
        return output_stl_path
        
    finally:
        try:
            os.unlink(scad_path)
        except:
            pass


def generate_stl_two_stage(letter1, letter2, font1, font2, size, 
                          relative_bail_x, relative_bail_y, relative_bail_z, pendant_rotation_y, 
                          frontend_center_x=0, frontend_center_y=0, frontend_center_z=0):
    """
    完整的兩階段生成流程
    
    返回: (final_stl_path, cleanup_files)
        final_stl_path: 最終 STL 檔案路徑
        cleanup_files: 需要清理的臨時檔案列表
    """
    
    logger.info("=" * 60)
    logger.info("🚀 開始兩階段 STL 生成")
    logger.info(f"   字母: {letter1} + {letter2}")
    logger.info(f"   字體: {font1} + {font2}")
    logger.info(f"   尺寸: {size}mm")
    logger.info(f"   相對墜頭: X={relative_bail_x:.3f}, Y={relative_bail_y:.3f}, Z={relative_bail_z:.3f}")
    logger.info(f"   旋轉: {pendant_rotation_y}°")
    logger.info("=" * 60)
    
    cleanup_files = []
    
    try:
        # === 第一階段：生成交集 ===
        logger.info("\n📦 Stage 1: 生成交集...")
        scad_intersection = generate_scad_intersection_only(letter1, letter2, font1, font2, size)
        
        temp_stl_1 = tempfile.NamedTemporaryFile(suffix='_stage1.stl', delete=False).name
        cleanup_files.append(temp_stl_1)
        
        env = os.environ.copy()
        env['DISPLAY'] = ':99'
        
        run_openscad(scad_intersection, temp_stl_1, env)
        logger.info(f"✅ Stage 1 完成: {temp_stl_1}")
        
        # === 使用前端的中心（不計算 STL） ===
        logger.info("\n📏 使用前端計算的 center...")
        center = np.array([frontend_center_x, frontend_center_y, frontend_center_z])
        logger.info(f"✅ 前端 Center: ({center[0]:.3f}, {center[1]:.3f}, {center[2]:.3f})")
        logger.info(f"✅ 相對墜頭位置: ({relative_bail_x:.3f}, {relative_bail_y:.3f}, {relative_bail_z:.3f})")
        
        # === 第二階段：居中 + 墜頭 ===
        logger.info("\n📦 Stage 2: 居中 + 墜頭...")
        scad_final = generate_scad_final_with_bail(
            temp_stl_1, center, 
            relative_bail_x, relative_bail_y, relative_bail_z,
            pendant_rotation_y
        )
        
        final_stl = tempfile.NamedTemporaryFile(suffix='_final.stl', delete=False).name
        cleanup_files.append(final_stl)
        
        run_openscad(scad_final, final_stl, env)
        logger.info(f"✅ Stage 2 完成: {final_stl}")
        
        logger.info("\n" + "=" * 60)
        logger.info("✅ 兩階段生成完成")
        logger.info("=" * 60)
        
        return final_stl, cleanup_files
        
    except Exception as e:
        logger.error(f"\n❌ 生成失敗: {e}")
        # 清理已創建的檔案
        for f in cleanup_files:
            try:
                if os.path.exists(f):
                    os.unlink(f)
            except:
                pass
        raise


# 保留舊的函數名以兼容現有代碼
def generate_scad_script(letter1, letter2, font1, font2, size, pendant_x, pendant_y, pendant_z, pendant_rotation_y):
    """
    舊版函數（兼容性）- 實際上會呼叫兩階段生成
    
    注意：這個函數現在返回 STL 檔案路徑而不是 SCAD 腳本
    """
    logger.warning("⚠️ 使用舊版 generate_scad_script，將自動切換到兩階段生成")
    final_stl, cleanup_files = generate_stl_two_stage(
        letter1, letter2, font1, font2, size,
        pendant_x, pendant_y, pendant_z, pendant_rotation_y
    )
    return final_stl, cleanup_files
