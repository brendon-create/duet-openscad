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

@app.route('/generate', methods=['POST'])
def generate_stl():
    """生成 STL 檔案的主要端點"""
    try:
        data = request.json
        logger.info(f"Received request: {data}")
        
        # 提取參數
        letter1 = data.get('letter1', 'D')
        letter2 = data.get('letter2', 'T')
        font1 = data.get('font1', 'Liberation Sans:style=Bold')
        font2 = data.get('font2', 'Liberation Sans:style=Bold')
        size = data.get('size', 20)
        pendant_config = data.get('pendant', {
            'x': 0,
            'y': 0,
            'z': 0,
            'rotation_y': 0
        })
        
        # 生成 OpenSCAD 腳本
        scad_content = generate_scad_script(
            letter1=letter1,
            letter2=letter2,
            font1=font1,
            font2=font2,
            size=size,
            pendant_x=pendant_config.get('x', 0),
            pendant_y=pendant_config.get('y', 0),
            pendant_z=pendant_config.get('z', 0),
            pendant_rotation_y=pendant_config.get('rotation_y', 0)
        )
        
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
