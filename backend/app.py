from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
import os
import subprocess
import tempfile
from scad_generator import generate_scad_script
import logging
import time
from collections import deque
from threading import Thread, Lock

# ==========================================
# Flask 應用初始化
# ==========================================

app = Flask(__name__)
CORS(app)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

TEMP_DIR = tempfile.gettempdir()
os.makedirs(TEMP_DIR, exist_ok=True)

# ==========================================
# 字體驗證
# ==========================================

def get_available_fonts():
    """獲取系統可用字體列表"""
    try:
        result = subprocess.run(
            ['fc-list', ':', 'family'],
            capture_output=True,
            text=True,
            timeout=5
        )
        
        if result.returncode != 0:
            logger.error(f"fc-list failed: {result.stderr}")
            return set()
        
        fonts = set()
        for line in result.stdout.strip().split('\n'):
            if line:
                # 提取純字體家族名稱（移除路徑和style）
                parts = line.split(':')
                if parts:
                    # 提取最後一個部分（家族名稱）
                    family_part = parts[-1] if ':' in line else parts[0]
                    # 移除 style 標記
                    family_name = family_part.split(',')[0].strip()
                    if family_name:
                        fonts.add(family_name)
        
        logger.info(f"找到 {len(fonts)} 個可用字體")
        return fonts
        
    except Exception as e:
        logger.error(f"獲取字體列表失敗: {e}")
        return set()

AVAILABLE_FONTS = get_available_fonts()

def validate_font(font_name):
    """驗證字體是否可用"""
    if font_name in AVAILABLE_FONTS:
        logger.info(f"字體 '{font_name}' 驗證通過")
        return font_name
    
    logger.warning(f"字體 '{font_name}' 不可用，使用 Sans")
    return "Sans"

# ==========================================
# STL 生成隊列系統
# ==========================================

stl_queue = deque()
queue_lock = Lock()
queue_results = {}

def process_queue():
    """背景線程處理 STL 生成隊列"""
    while True:
        try:
            with queue_lock:
                if not stl_queue:
                    time.sleep(0.5)
                    continue
                
                order_id, items = stl_queue.popleft()
                logger.info(f"📋 隊列中有 {len(stl_queue) + 1} 個待處理項目")
            
            logger.info(f"🔨 處理訂單: {order_id}")
            logger.info(f"🔨 開始生成訂單 {order_id} 的 STL...")
            
            stl_files = []
            
            for idx, item in enumerate(items, 1):
                try:
                    logger.info(f"🔨 生成 STL: {item['letter1']}{item['letter2']}")
                    
                    # 簡化參數提取
                    params = {
                        'letter1': item['letter1'],
                        'letter2': item['letter2'],
                        'font1': item['font1'],
                        'font2': item['font2'],
                        'size': item['size'],
                        'bailRelativeX': item.get('bailRelativeX', 0),
                        'bailRelativeY': item.get('bailRelativeY', 0),
                        'bailRelativeZ': item.get('bailRelativeZ', 0),
                        'bailRotation': item.get('bailRotation', 0)
                    }
                    
                    scad_content = generate_scad_script(**params)
                    
                    # 生成 STL
                    with tempfile.NamedTemporaryFile(mode='w', suffix='.scad', delete=False) as scad_file:
                        scad_file.write(scad_content)
                        scad_path = scad_file.name
                    
                    stl_path = scad_path.replace('.scad', '.stl')
                    filename = f"{item['letter1']}{item['letter2']}_{item['size']}mm.stl"
                    
                    try:
                        subprocess.run(
                            ['openscad', '-o', stl_path, scad_path],
                            check=True,
                            capture_output=True,
                            timeout=300
                        )
                        
                        if os.path.exists(stl_path) and os.path.getsize(stl_path) > 0:
                            stl_files.append((stl_path, filename))
                            logger.info(f"✅ STL {idx}/{len(items)} 生成成功")
                        else:
                            logger.error(f"❌ STL {idx}/{len(items)} 檔案無效")
                            
                    except subprocess.TimeoutExpired:
                        logger.error(f"❌ STL {idx}/{len(items)} 生成超時")
                    except subprocess.CalledProcessError as e:
                        logger.error(f"❌ OpenSCAD 錯誤: {e.stderr.decode()}")
                    finally:
                        if os.path.exists(scad_path):
                            os.unlink(scad_path)
                            
                except Exception as e:
                    logger.error(f"❌ STL 生成錯誤: {e}")
                    import traceback
                    traceback.print_exc()
            
            with queue_lock:
                queue_results[order_id] = {
                    'status': 'completed' if stl_files else 'failed',
                    'files': stl_files,
                    'timestamp': time.time()
                }
                
            logger.info(f"✅ 訂單 {order_id} 處理完成，生成 {len(stl_files)}/{len(items)} 個 STL")
            
        except Exception as e:
            logger.error(f"❌ 隊列處理錯誤: {e}")
            import traceback
            traceback.print_exc()
            time.sleep(1)

# 啟動背景線程
Thread(target=process_queue, daemon=True).start()

# ==========================================
# API 端點
# ==========================================

@app.route('/health', methods=['GET'])
def health():
    """健康檢查"""
    return jsonify({
        'status': 'ok',
        'engine': 'OpenSCAD',
        'queue_size': len(stl_queue)
    })

@app.route('/list-fonts', methods=['GET'])
def list_fonts():
    """列出可用字體"""
    return jsonify({
        'fonts': sorted(list(AVAILABLE_FONTS)),
        'count': len(AVAILABLE_FONTS)
    })

@app.route('/generate', methods=['POST'])
def generate_single():
    """單個 STL 生成（立即返回）"""
    try:
        data = request.json
        
        letter1 = data.get('letter1', 'A').upper()
        letter2 = data.get('letter2', 'B').upper()
        font1 = validate_font(data.get('font1', 'Abel'))
        font2 = validate_font(data.get('font2', 'Alice'))
        size = int(data.get('size', 15))
        
        # 支援多種參數格式
        if 'bailRelativeX' in data:
            bailRelativeX = data.get('bailRelativeX', 0)
            bailRelativeY = data.get('bailRelativeY', 0)
            bailRelativeZ = data.get('bailRelativeZ', 0)
            bailRotation = data.get('bailRotation', 0)
        elif 'bailX' in data:
            # 向後相容舊格式
            bailRelativeX = data.get('bailX', 0)
            bailRelativeY = data.get('bailY', 0)
            bailRelativeZ = data.get('bailZ', 0)
            bailRotation = data.get('bailRotation', 0)
        else:
            bailRelativeX = bailRelativeY = bailRelativeZ = bailRotation = 0
        
        logger.info(f"收到請求: {letter1}+{letter2}, size={size}")
        logger.info(f"墜頭相對位置: X={bailRelativeX}, Y={bailRelativeY}, Z={bailRelativeZ}, Rotation={bailRotation}")
        
        scad_content = generate_scad_script(
            letter1=letter1,
            letter2=letter2,
            font1=font1,
            font2=font2,
            size=size,
            bailRelativeX=bailRelativeX,
            bailRelativeY=bailRelativeY,
            bailRelativeZ=bailRelativeZ,
            bailRotation=bailRotation
        )
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.scad', delete=False) as scad_file:
            scad_file.write(scad_content)
            scad_path = scad_file.name
        
        stl_path = scad_path.replace('.scad', '.stl')
        
        try:
            result = subprocess.run(
                ['openscad', '-o', stl_path, scad_path],
                check=True,
                capture_output=True,
                text=True,
                timeout=300
            )
            
            if result.returncode != 0:
                logger.error(f"OpenSCAD stderr: {result.stderr}")
            
            if not os.path.exists(stl_path) or os.path.getsize(stl_path) == 0:
                raise Exception("STL 檔案生成失敗或為空")
            
            logger.info(f"✅ STL 生成成功: {os.path.getsize(stl_path)} bytes")
            
            return send_file(
                stl_path,
                mimetype='application/sla',
                as_attachment=True,
                download_name=f'{letter1}{letter2}_DUET.stl'
            )
            
        except subprocess.TimeoutExpired:
            logger.error("OpenSCAD 執行超時")
            return jsonify({'error': 'STL 生成超時'}), 500
        except Exception as e:
            logger.error(f"STL 生成錯誤: {e}")
            return jsonify({'error': str(e)}), 500
        finally:
            if os.path.exists(scad_path):
                os.unlink(scad_path)
                
    except Exception as e:
        logger.error(f"請求處理錯誤: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/generate-batch', methods=['POST'])
def generate_batch():
    """批量 STL 生成（加入隊列）"""
    try:
        data = request.json
        items = data.get('items', [])
        
        if not items:
            return jsonify({'error': '沒有項目'}), 400
        
        order_id = data.get('order_id', f'ORDER_{int(time.time() * 1000)}')
        
        with queue_lock:
            stl_queue.append((order_id, items))
        
        logger.info(f"✅ 訂單 {order_id} 已加入隊列，共 {len(items)} 個項目")
        
        return jsonify({
            'message': '已加入生成隊列',
            'order_id': order_id,
            'items_count': len(items)
        })
        
    except Exception as e:
        logger.error(f"批量生成請求錯誤: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/check-order/<order_id>', methods=['GET'])
def check_order(order_id):
    """檢查訂單狀態"""
    with queue_lock:
        if order_id in queue_results:
            result = queue_results[order_id]
            return jsonify({
                'status': result['status'],
                'files_count': len(result['files']),
                'timestamp': result['timestamp']
            })
        else:
            # 檢查是否還在隊列中
            for qid, _ in stl_queue:
                if qid == order_id:
                    return jsonify({'status': 'processing'})
            
            return jsonify({'status': 'not_found'}), 404

@app.route('/download-order/<order_id>', methods=['GET'])
def download_order(order_id):
    """下載訂單的所有 STL 文件（打包為 ZIP）"""
    try:
        with queue_lock:
            if order_id not in queue_results:
                return jsonify({'error': '訂單不存在'}), 404
            
            result = queue_results[order_id]
            
            if result['status'] != 'completed':
                return jsonify({'error': '訂單尚未完成'}), 400
            
            files = result['files']
        
        if not files:
            return jsonify({'error': '沒有可下載的文件'}), 404
        
        # 如果只有一個文件，直接下載
        if len(files) == 1:
            stl_path, filename = files[0]
            return send_file(
                stl_path,
                mimetype='application/sla',
                as_attachment=True,
                download_name=filename
            )
        
        # 多個文件，打包為 ZIP
        import zipfile
        zip_path = os.path.join(TEMP_DIR, f'{order_id}.zip')
        
        with zipfile.ZipFile(zip_path, 'w') as zipf:
            for stl_path, filename in files:
                zipf.write(stl_path, filename)
        
        return send_file(
            zip_path,
            mimetype='application/zip',
            as_attachment=True,
            download_name=f'{order_id}.zip'
        )
        
    except Exception as e:
        logger.error(f"下載訂單錯誤: {e}")
        return jsonify({'error': str(e)}), 500

# ==========================================
# 主程序
# ==========================================

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=False)
