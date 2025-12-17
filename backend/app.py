from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
import os
import subprocess
import tempfile
from scad_generator_new import generate_stl_two_stage
import logging

app = Flask(__name__)
CORS(app)

# 設定日誌
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# 確保臨時目錄存在
TEMP_DIR = tempfile.gettempdir()
os.makedirs(TEMP_DIR, exist_ok=True)

@app.route('/health', methods=['GET'])
def health_check():
    """健康檢查端點"""
    try:
        # 檢查 OpenSCAD 是否可用 (使用 which 指令)
        result = subprocess.run(['which', 'openscad'], 
                              capture_output=True, 
                              text=True, 
                              timeout=5)
        if result.returncode == 0:
            openscad_path = result.stdout.strip()
            # 嘗試取得版本
            version_result = subprocess.run(['openscad', '--version'], 
                                          capture_output=True, 
                                          text=True, 
                                          timeout=5,
                                          env={'DISPLAY': ':99'})  # 使用 xvfb
            version_info = version_result.stdout.strip() or version_result.stderr.strip() or "Installed"
            openscad_status = f"{openscad_path} - {version_info}"
        else:
            openscad_status = "Not found"
    except Exception as e:
        openscad_status = f"Error: {str(e)}"
    
    return jsonify({
        'status': 'healthy',
        'openscad': openscad_status,
        'temp_dir': TEMP_DIR
    })

def get_available_fonts():
    """
    獲取系統中所有可用的字體家族名稱
    從 fc-list 輸出中提取純字體名稱（移除路徑和 style）
    """
    try:
        result = subprocess.run(
            ['fc-list'],  # 不用 :family，獲取完整信息
            capture_output=True,
            text=True,
            timeout=10
        )
        
        if result.returncode != 0:
            return set()
        
        font_families = set()
        for line in result.stdout.strip().split('\n'):
            if line and ':' in line:
                # 格式: /path/to/font.ttf: Family Name:style=Style
                # 或: /path/to/font.ttf: Family Name
                parts = line.split(':', 1)
                if len(parts) >= 2:
                    font_info = parts[1].strip()
                    
                    # 移除 style 資訊
                    if ':style=' in font_info:
                        font_name = font_info.split(':style=')[0].strip()
                    else:
                        font_name = font_info.strip()
                    
                    # 處理逗號分隔的別名
                    for name in font_name.split(','):
                        clean_name = name.strip()
                        if clean_name:
                            font_families.add(clean_name)
        
        return font_families
        
    except Exception as e:
        logger.error(f"Error getting available fonts: {e}")
        return set()

def validate_font(font_name):
    """
    嚴格驗證字體是否存在
    如果字體不存在，拋出錯誤
    """
    logger.info(f"Validating font: {font_name}")
    
    # 獲取可用字體清單
    available_fonts = get_available_fonts()
    
    if not available_fonts:
        logger.error("Could not retrieve font list from system")
        raise ValueError("無法獲取系統字體清單")
    
    # 嚴格檢查字體是否存在
    if font_name not in available_fonts:
        logger.error(f"Font '{font_name}' not found in system. Available fonts: {len(available_fonts)}")
        raise ValueError(f"字體 '{font_name}' 不存在。請從字體選單中選擇可用的字體。")
    
    logger.info(f"Font '{font_name}' validated successfully")
    return font_name

@app.route('/list-fonts', methods=['GET'])
def list_fonts():
    """
    列出系統中所有可用的字體家族名稱（用於前端過濾）
    返回格式：{"fonts": ["Roboto", "Alex Brush", ...]}
    """
    try:
        # 使用 fc-list 列出所有字體（包含完整信息）
        result = subprocess.run(
            ['fc-list'],  # 移除 :family 參數
            capture_output=True,
            text=True,
            timeout=10
        )
        
        if result.returncode != 0:
            logger.error(f"fc-list failed: {result.stderr}")
            return jsonify({'error': 'Failed to list fonts'}), 500
        
        # 解析字體名稱
        # fc-list 的輸出格式：
        # /path/to/font.ttf: Family Name:style=Style
        # 提取純字體家族名稱
        font_families = set()
        for line in result.stdout.strip().split('\n'):
            if line and ':' in line:
                parts = line.split(':', 1)
                if len(parts) >= 2:
                    font_info = parts[1].strip()
                    
                    # 移除 style 資訊
                    if ':style=' in font_info:
                        font_name = font_info.split(':style=')[0].strip()
                    else:
                        font_name = font_info.strip()
                    
                    # 處理多個家族名稱（逗號分隔）
                    for family in font_name.split(','):
                        clean_name = family.strip()
                        if clean_name:
                            font_families.add(clean_name)
        
        # 排序並返回
        sorted_fonts = sorted(font_families)
        logger.info(f"Found {len(sorted_fonts)} unique font families")
        
        return jsonify({
            'fonts': sorted_fonts,
            'total': len(sorted_fonts)
        })
        
    except Exception as e:
        logger.error(f"Error in list_fonts: {e}")
        return jsonify({'error': 'Internal server error'}), 500

@app.route('/generate', methods=['POST'])
def generate_stl():
    """生成 STL 檔案的主要端點"""
    try:
        data = request.json
        logger.info(f"Received request: {data}")
        
        # 提取參數
        letter1 = data.get('letter1', 'D')
        letter2 = data.get('letter2', 'T')
        font1 = data.get('font1', 'Roboto')
        font2 = data.get('font2', 'Roboto')
        size = data.get('size', 20)
        
        # 支援兩種參數格式：新版（相對位置）或舊版
        if 'relativeBailX' in data:
            # ✅ 新版：使用相對位置
            relative_bail_x = data.get('relativeBailX', 0)
            relative_bail_y = data.get('relativeBailY', 0)
            relative_bail_z = data.get('relativeBailZ', 0)
            pendant_rotation = data.get('bailRotation', 0)
            # 前端的主體中心
            model_center_x = data.get('modelCenterX', 0)
            model_center_y = data.get('modelCenterY', 0)
            model_center_z = data.get('modelCenterZ', 0)
            logger.info(f"✅ 使用相對位置模式")
            logger.info(f"   相對墜頭位置: ({relative_bail_x:.3f}, {relative_bail_y:.3f}, {relative_bail_z:.3f})")
        elif 'bailX' in data:
            # 舊版：扁平格式（向後兼容）
            pendant_x = data.get('bailX', 0)
            pendant_y = data.get('bailY', 0)
            pendant_z = data.get('bailZ', 0)
            pendant_rotation = data.get('bailRotation', 0)
            model_center_x = data.get('modelCenterX', 0)
            model_center_y = data.get('modelCenterY', 0)
            model_center_z = data.get('modelCenterZ', 0)
            # 計算相對位置
            relative_bail_x = pendant_x
            relative_bail_y = pendant_y
            relative_bail_z = pendant_z
            logger.info(f"⚠️ 使用舊版格式（向後兼容）")
        else:
            # 更舊版：嵌套格式
            pendant_config = data.get('pendant', {})
            pendant_x = pendant_config.get('x', 0)
            pendant_y = pendant_config.get('y', 0)
            pendant_z = pendant_config.get('z', 0)
            pendant_rotation = pendant_config.get('rotation_y', 0)
            model_center_x = 0
            model_center_y = 0
            model_center_z = 0
            relative_bail_x = pendant_x
            relative_bail_y = pendant_y
            relative_bail_z = pendant_z
            logger.info(f"⚠️ 使用最舊版格式")
        
        logger.info(f"🎯 墜頭旋轉: {pendant_rotation}°")
        logger.info(f"📍 主體中心 (前端): ({model_center_x:.3f}, {model_center_y:.3f}, {model_center_z:.3f})")
        
        # 驗證並標準化字體名稱
        font1 = validate_font(font1)
        font2 = validate_font(font2)
        
        # ✅ 使用兩階段生成（相對位置模式）
        stl_path, cleanup_files = generate_stl_two_stage(
            letter1=letter1,
            letter2=letter2,
            font1=font1,
            font2=font2,
            size=size,
            relative_bail_x=relative_bail_x,
            relative_bail_y=relative_bail_y,
            relative_bail_z=relative_bail_z,
            pendant_rotation_y=pendant_rotation,
            frontend_center_x=model_center_x,
            frontend_center_y=model_center_y,
            frontend_center_z=model_center_z
        )
        
        logger.info(f"✅ STL generated successfully: {stl_path}")
        
        # 發送檔案
        response = send_file(
            stl_path,
            mimetype='application/octet-stream',
            as_attachment=True,
            download_name=f'{letter1}{letter2}_DUET.stl'
        )
        
        # 清理臨時檔案 (在 response 後)
        @response.call_on_close
        def cleanup():
            try:
                for f in cleanup_files:
                    if os.path.exists(f):
                        os.unlink(f)
                logger.info("Temporary files cleaned up")
            except Exception as e:
                logger.warning(f"Cleanup error: {e}")
        
        return response
        
    except Exception as e:
        logger.error(f"Error in generate_stl: {str(e)}", exc_info=True)
        return jsonify({
            'error': 'Internal server error',
            'details': str(e)
        }), 500

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
