from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
import os
import subprocess
import tempfile
from scad_generator import generate_scad_script
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

def validate_font(font_name):
    """
    驗證並標準化字體名稱
    使用 fc-match 查找系統中的最佳匹配字體
    """
    logger.info(f"Requesting font: {font_name}")
    
    try:
        # 使用 fc-match 找到最佳匹配的字體
        result = subprocess.run(
            ['fc-match', '-f', '%{family}', font_name],
            capture_output=True,
            text=True,
            timeout=5
        )
        
        if result.returncode == 0:
            matched_font = result.stdout.strip()
            if matched_font:
                logger.info(f"Font '{font_name}' matched to '{matched_font}'")
                return matched_font
        
        # 如果 fc-match 失敗，返回原字體名稱
        logger.warning(f"Could not match font '{font_name}', using as-is")
        return font_name
        
    except Exception as e:
        logger.error(f"Error matching font '{font_name}': {e}")
        return font_name

@app.route('/list-fonts', methods=['GET'])
def list_fonts():
    """列出系統中所有可用的字體（除錯用）"""
    try:
        result = subprocess.run(
            ['fc-list', ':family'],
            capture_output=True,
            text=True,
            timeout=10
        )
        fonts = sorted(set(result.stdout.strip().split('\n')))
        return jsonify({
            'total': len(fonts),
            'fonts': fonts
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

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
        
        # 支援兩種參數格式：扁平或嵌套
        if 'bailX' in data:
            # 扁平格式（前端發送的）
            pendant_x = data.get('bailX', 0)
            pendant_y = data.get('bailY', 0)
            pendant_z = data.get('bailZ', 0)
            pendant_rotation = data.get('bailRotation', 0)
        else:
            # 嵌套格式（舊版）
            pendant_config = data.get('pendant', {})
            pendant_x = pendant_config.get('x', 0)
            pendant_y = pendant_config.get('y', 0)
            pendant_z = pendant_config.get('z', 0)
            pendant_rotation = pendant_config.get('rotation_y', 0)
        
        logger.info(f"Pendant params: x={pendant_x}, y={pendant_y}, z={pendant_z}, rotation={pendant_rotation}")
        
        # 驗證並標準化字體名稱
        font1 = validate_font(font1)
        font2 = validate_font(font2)
        
        # 生成 OpenSCAD 腳本
        scad_content = generate_scad_script(
            letter1=letter1,
            letter2=letter2,
            font1=font1,
            font2=font2,
            size=size,
            pendant_x=pendant_x,
            pendant_y=pendant_y,
            pendant_z=pendant_z,
            pendant_rotation_y=pendant_rotation
        )
        
        # 記錄 Letter 2 的旋轉邏輯（用於驗證版本）
        if 'rotate([0, 0, 90])' in scad_content:
            logger.info("✅ Using nested rotation (correct version)")
        elif 'rotate([90, 0, 90])' in scad_content:
            logger.info("❌ Using single rotation (old version)")
        else:
            logger.warning("⚠️ Rotation pattern not recognized")
        
        # 建立臨時檔案
        with tempfile.NamedTemporaryFile(mode='w', suffix='.scad', delete=False) as scad_file:
            scad_file.write(scad_content)
            scad_path = scad_file.name
        
        stl_path = scad_path.replace('.scad', '.stl')
        
        logger.info(f"SCAD file: {scad_path}")
        logger.info(f"STL file: {stl_path}")
        
        # 執行 OpenSCAD (使用 xvfb 虛擬顯示)
        cmd = [
            'openscad',
            '-o', stl_path,
            '--export-format', 'binstl',
            scad_path
        ]
        
        logger.info(f"Running command: {' '.join(cmd)}")
        
        # 設定環境變數使用 xvfb
        env = os.environ.copy()
        env['DISPLAY'] = ':99'
        
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=180,  # 3 分鐘 - 支援高精度參數
            env=env
        )
        
        if result.returncode != 0:
            logger.error(f"OpenSCAD error: {result.stderr}")
            return jsonify({
                'error': 'OpenSCAD execution failed',
                'details': result.stderr
            }), 500
        
        # 檢查 STL 檔案是否生成
        if not os.path.exists(stl_path):
            logger.error("STL file not generated")
            return jsonify({
                'error': 'STL file not generated'
            }), 500
        
        logger.info(f"STL generated successfully: {stl_path}")
        
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
                os.unlink(scad_path)
                os.unlink(stl_path)
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
