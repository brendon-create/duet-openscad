"""
DUET Backend - 帶隊列系統的版本
包含：STL 生成、綠界金流、Email 發送、異步 STL 處理
"""

from flask import Flask, request, jsonify, send_file, redirect
from flask_cors import CORS
import os
import subprocess
import tempfile
from scad_generator import generate_scad_script
import logging
import hashlib
import urllib.parse
from datetime import datetime
import json
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders
import threading
import time

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
# 配置區塊
# ==========================================

# 綠界配置
ECPAY_CONFIG = {
    'MerchantID': '3317971',
    'HashKey': 'MN7lld33ls2A7ACQ',
    'HashIV': 'JsQNlwsz3QtbVKIq',
    'PaymentURL': 'https://payment.ecpay.com.tw/Cashier/AioCheckOut/V5'
}

# Email 配置
EMAIL_CONFIG = {
    'smtp_server': 'smtp.gmail.com',
    'smtp_port': 587,
    'sender_email': 'service@brendonchen.com',
    'sender_password': 'ptja xltm uoeh basi',  # ← 更新這裡
    'sender_name': 'DUET 客製珠寶',
    'internal_email': 'brendon@brendonchen.com'
}

# 目錄配置
ORDERS_DIR = 'orders'
STL_DIR = 'stl_files'
QUEUE_DIR = 'stl_queue'  # 新增：STL 生成隊列
os.makedirs(ORDERS_DIR, exist_ok=True)
os.makedirs(STL_DIR, exist_ok=True)
os.makedirs(QUEUE_DIR, exist_ok=True)

# ==========================================
# 隊列系統
# ==========================================

def add_to_stl_queue(order_id, retry_count=0):
    """將訂單加入 STL 生成隊列"""
    queue_item = {
        'order_id': order_id,
        'added_at': datetime.now().isoformat(),
        'retry_count': retry_count,
        'status': 'pending'
    }
    
    queue_file = os.path.join(QUEUE_DIR, f'{order_id}.json')
    with open(queue_file, 'w', encoding='utf-8') as f:
        json.dump(queue_item, f, ensure_ascii=False, indent=2)
    
    logger.info(f"✅ 訂單 {order_id} 已加入 STL 生成隊列")

def get_pending_queue_items():
    """取得待處理的隊列項目"""
    items = []
    try:
        for filename in os.listdir(QUEUE_DIR):
            if filename.endswith('.json'):
                filepath = os.path.join(QUEUE_DIR, filename)
                try:
                    with open(filepath, 'r', encoding='utf-8') as f:
                        item = json.load(f)
                        if item.get('status') == 'pending':
                            items.append((filepath, item))
                except Exception as e:
                    logger.error(f"讀取隊列項目錯誤 {filename}: {e}")
    except Exception as e:
        logger.error(f"讀取隊列目錄錯誤: {e}")
    
    return items

def remove_from_queue(queue_file):
    """從隊列移除項目"""
    try:
        os.unlink(queue_file)
        logger.info(f"✅ 已從隊列移除: {queue_file}")
    except Exception as e:
        logger.error(f"移除隊列項目錯誤: {e}")

def process_stl_queue():
    """處理 STL 生成隊列（背景執行）"""
    logger.info("🔄 開始處理 STL 隊列...")
    
    items = get_pending_queue_items()
    
    if not items:
        logger.info("📭 隊列為空")
        return
    
    logger.info(f"📋 隊列中有 {len(items)} 個待處理項目")
    
    # 每次只處理一個，避免記憶體問題
    queue_file, item = items[0]
    order_id = item['order_id']
    retry_count = item.get('retry_count', 0)
    
    logger.info(f"🔨 處理訂單: {order_id} (重試次數: {retry_count})")
    
    try:
        # 生成 STL 並發送 Email
        success = generate_and_send_stl(order_id)
        
        if success:
            # 成功：從隊列移除
            remove_from_queue(queue_file)
            update_order_status(order_id, 'completed')
            logger.info(f"✅ 訂單 {order_id} 處理完成")
        else:
            # 失敗：重試或通知
            if retry_count < 3:
                # 更新重試次數
                item['retry_count'] = retry_count + 1
                item['last_retry'] = datetime.now().isoformat()
                with open(queue_file, 'w', encoding='utf-8') as f:
                    json.dump(item, f, ensure_ascii=False, indent=2)
                logger.warning(f"⚠️ 訂單 {order_id} 處理失敗，將重試 ({retry_count + 1}/3)")
            else:
                # 重試 3 次後仍失敗
                item['status'] = 'failed'
                with open(queue_file, 'w', encoding='utf-8') as f:
                    json.dump(item, f, ensure_ascii=False, indent=2)
                update_order_status(order_id, 'stl_failed')
                send_admin_alert(order_id, "STL 生成失敗，已重試 3 次")
                logger.error(f"❌ 訂單 {order_id} 處理失敗，已重試 3 次")
                
    except Exception as e:
        logger.error(f"❌ 處理隊列項目時發生錯誤: {str(e)}")
        # 不移除，下次再試

def stl_queue_worker():
    """背景 Worker：定期處理隊列"""
    logger.info("🚀 STL Queue Worker 已啟動")
    
    while True:
        try:
            process_stl_queue()
        except Exception as e:
            logger.error(f"Worker 錯誤: {str(e)}")
        
        # 每 60 秒檢查一次
        time.sleep(60)

# 啟動背景 Worker
def start_background_worker():
    """在背景線程啟動 Worker"""
    worker_thread = threading.Thread(target=stl_queue_worker, daemon=True)
    worker_thread.start()
    logger.info("✅ 背景 Worker 已啟動")

# ==========================================
# STL 生成和發送
# ==========================================

def generate_stl_for_item(item):
    """為單個商品生成 STL"""
    try:
        logger.info(f"🔨 生成 STL: {item['letter1']}{item['letter2']}")
        
        # 準備參數
        params = {
            'letter1': item['letter1'],
            'letter2': item['letter2'],
            'font1': item['font1'],
            'font2': item['font2'],
            'size': item['size'],
            'bailRelativeX': item.get('bailRelativeX', 0),
            'bailRelativeY': item.get('bailRelativeY', 0),
            'bailRelativeZ': item.get('bailRelativeZ', 0),
            'bailRotation': item.get('bailRotation', 0),
            'bailAbsoluteX': item.get('bailAbsoluteX', 0),
            'bailAbsoluteY': item.get('bailAbsoluteY', 0),
            'bailAbsoluteZ': item.get('bailAbsoluteZ', 0),
            'letter1Width': item.get('letter1BBox', {}).get('width', 0),
            'letter1Height': item.get('letter1BBox', {}).get('height', 0),
            'letter1Depth': item.get('letter1BBox', {}).get('depth', 0),
            'letter1OffsetX': item.get('letter1BBox', {}).get('offsetX', 0),
            'letter1OffsetY': item.get('letter1BBox', {}).get('offsetY', 0),
            'letter1OffsetZ': item.get('letter1BBox', {}).get('offsetZ', 0),
            'letter2Width': item.get('letter2BBox', {}).get('width', 0),
            'letter2Height': item.get('letter2BBox', {}).get('height', 0),
            'letter2Depth': item.get('letter2BBox', {}).get('depth', 0),
            'letter2OffsetX': item.get('letter2BBox', {}).get('offsetX', 0),
            'letter2OffsetY': item.get('letter2BBox', {}).get('offsetY', 0),
            'letter2OffsetZ': item.get('letter2BBox', {}).get('offsetZ', 0)
        }
        
        # 生成 SCAD 腳本
        scad_content = generate_scad_script(**params)
        
        # 寫入臨時檔案
        with tempfile.NamedTemporaryFile(mode='w', suffix='.scad', delete=False) as scad_file:
            scad_file.write(scad_content)
            scad_path = scad_file.name
        
        # 生成 STL
        stl_path = scad_path.replace('.scad', '.stl')
        
        cmd = [
            'openscad',
            '-o', stl_path,
            '--export-format', 'binstl',
            scad_path
        ]
        
        env = os.environ.copy()
        env['DISPLAY'] = ':99'
        
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=180,
            env=env
        )
        
        # 清理 SCAD 檔案
        try:
            os.unlink(scad_path)
        except:
            pass
        
        if result.returncode != 0 or not os.path.exists(stl_path):
            logger.error(f"❌ STL 生成失敗: {result.stderr}")
            return None
        
        # 複製到永久目錄
        final_path = os.path.join(STL_DIR, f"{item['id']}.stl")
        import shutil
        shutil.copy(stl_path, final_path)
        
        # 清理臨時 STL
        try:
            os.unlink(stl_path)
        except:
            pass
        
        logger.info(f"✅ STL 已生成: {final_path}")
        return final_path
        
    except Exception as e:
        logger.error(f"❌ STL 生成錯誤: {str(e)}")
        return None

def generate_and_send_stl(order_id):
    """生成訂單的所有 STL 並發送 Email"""
    try:
        order = load_order(order_id)
        if not order:
            return False
        
        logger.info(f"🔨 開始生成訂單 {order_id} 的 STL...")
        
        stl_files = []
        for item in order['items']:
            stl_path = generate_stl_for_item(item)
            if stl_path:
                stl_files.append(stl_path)
            else:
                logger.error(f"❌ 項目 {item.get('id')} 的 STL 生成失敗")
                return False
        
        # 發送帶 STL 的 Email
        email_sent = send_stl_email(order, stl_files)
        
        return email_sent
        
    except Exception as e:
        logger.error(f"❌ generate_and_send_stl 錯誤: {str(e)}")
        return False

# ==========================================
# 原有的 STL 生成端點（保留）
# ==========================================

@app.route('/health', methods=['GET'])
def health_check():
    try:
        result = subprocess.run(['which', 'openscad'], 
                              capture_output=True, 
                              text=True, 
                              timeout=5)
        if result.returncode == 0:
            openscad_path = result.stdout.strip()
            version_result = subprocess.run(['openscad', '--version'], 
                                          capture_output=True, 
                                          text=True, 
                                          timeout=5,
                                          env={'DISPLAY': ':99'})
            version_info = version_result.stdout.strip() or version_result.stderr.strip() or "Installed"
            openscad_status = f"{openscad_path} - {version_info}"
        else:
            openscad_status = "Not found"
    except Exception as e:
        openscad_status = f"Error: {str(e)}"
    
    # 檢查隊列狀態
    queue_items = get_pending_queue_items()
    
    return jsonify({
        'status': 'healthy',
        'openscad': openscad_status,
        'temp_dir': TEMP_DIR,
        'payment_enabled': True,
        'email_enabled': True,
        'queue_system': True,
        'pending_stl_jobs': len(queue_items)
    })

def get_available_fonts():
    try:
        result = subprocess.run(
            ['fc-list'],
            capture_output=True,
            text=True,
            timeout=10
        )
        
        if result.returncode != 0:
            return set()
        
        font_families = set()
        for line in result.stdout.strip().split('\n'):
            if line and ':' in line:
                parts = line.split(':', 1)
                if len(parts) >= 2:
                    font_info = parts[1].strip()
                    
                    if ':style=' in font_info:
                        font_name = font_info.split(':style=')[0].strip()
                    else:
                        font_name = font_info.strip()
                    
                    for name in font_name.split(','):
                        clean_name = name.strip()
                        if clean_name:
                            font_families.add(clean_name)
        
        return font_families
        
    except Exception as e:
        logger.error(f"Error getting available fonts: {e}")
        return set()

def validate_font(font_name):
    logger.info(f"Validating font: {font_name}")
    
    available_fonts = get_available_fonts()
    
    if not available_fonts:
        logger.error("Could not retrieve font list from system")
        raise ValueError("Cannot get system fonts")
    
    if font_name not in available_fonts:
        logger.error(f"Font '{font_name}' not found in system. Available fonts: {len(available_fonts)}")
        raise ValueError(f"Font '{font_name}' not found")
    
    logger.info(f"Font '{font_name}' validated successfully")
    return font_name

@app.route('/list-fonts', methods=['GET'])
def list_fonts():
    try:
        result = subprocess.run(
            ['fc-list'],
            capture_output=True,
            text=True,
            timeout=10
        )
        
        if result.returncode != 0:
            logger.error(f"fc-list failed: {result.stderr}")
            return jsonify({'error': 'Failed to list fonts'}), 500
        
        font_families = set()
        for line in result.stdout.strip().split('\n'):
            if line and ':' in line:
                parts = line.split(':', 1)
                if len(parts) >= 2:
                    font_info = parts[1].strip()
                    
                    if ':style=' in font_info:
                        font_name = font_info.split(':style=')[0].strip()
                    else:
                        font_name = font_info.strip()
                    
                    for family in font_name.split(','):
                        clean_name = family.strip()
                        if clean_name:
                            font_families.add(clean_name)
        
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
    """原有的即時 STL 生成端點（保留供前端預覽使用）"""
    try:
        data = request.json
        logger.info(f"Received request: {data}")
        
        letter1 = data.get('letter1', 'D')
        letter2 = data.get('letter2', 'T')
        font1 = data.get('font1', 'Roboto')
        font2 = data.get('font2', 'Roboto')
        size = data.get('size', 20)
        
        if 'bailRelativeX' in data:
            bailRelativeX = data.get('bailRelativeX', 0)
            bailRelativeY = data.get('bailRelativeY', 0)
            bailRelativeZ = data.get('bailRelativeZ', 0)
            bailRotation = data.get('bailRotation', 0)
        elif 'bailX' in data:
            bailRelativeX = data.get('bailX', 0)
            bailRelativeY = data.get('bailY', 0)
            bailRelativeZ = data.get('bailZ', 0)
            bailRotation = data.get('bailRotation', 0)
        else:
            pendant_config = data.get('pendant', {})
            bailRelativeX = pendant_config.get('x', 0)
            bailRelativeY = pendant_config.get('y', 0)
            bailRelativeZ = pendant_config.get('z', 0)
            bailRotation = pendant_config.get('rotation_y', 0)
        
        bailAbsoluteX = data.get('bailAbsoluteX', 0)
        bailAbsoluteY = data.get('bailAbsoluteY', 0)
        bailAbsoluteZ = data.get('bailAbsoluteZ', 0)
        
        letter1Width = data.get('letter1Width', 0)
        letter1Height = data.get('letter1Height', 0)
        letter1Depth = data.get('letter1Depth', 0)
        letter1OffsetX = data.get('letter1OffsetX', 0)
        letter1OffsetY = data.get('letter1OffsetY', 0)
        letter1OffsetZ = data.get('letter1OffsetZ', 0)
        
        letter2Width = data.get('letter2Width', 0)
        letter2Height = data.get('letter2Height', 0)
        letter2Depth = data.get('letter2Depth', 0)
        letter2OffsetX = data.get('letter2OffsetX', 0)
        letter2OffsetY = data.get('letter2OffsetY', 0)
        letter2OffsetZ = data.get('letter2OffsetZ', 0)
        
        font1 = validate_font(font1)
        font2 = validate_font(font2)
        
        scad_content = generate_scad_script(
            letter1=letter1,
            letter2=letter2,
            font1=font1,
            font2=font2,
            size=size,
            bailRelativeX=bailRelativeX,
            bailRelativeY=bailRelativeY,
            bailRelativeZ=bailRelativeZ,
            bailRotation=bailRotation,
            bailAbsoluteX=bailAbsoluteX,
            bailAbsoluteY=bailAbsoluteY,
            bailAbsoluteZ=bailAbsoluteZ,
            letter1Width=letter1Width,
            letter1Height=letter1Height,
            letter1Depth=letter1Depth,
            letter1OffsetX=letter1OffsetX,
            letter1OffsetY=letter1OffsetY,
            letter1OffsetZ=letter1OffsetZ,
            letter2Width=letter2Width,
            letter2Height=letter2Height,
            letter2Depth=letter2Depth,
            letter2OffsetX=letter2OffsetX,
            letter2OffsetY=letter2OffsetY,
            letter2OffsetZ=letter2OffsetZ
        )
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.scad', delete=False) as scad_file:
            scad_file.write(scad_content)
            scad_path = scad_file.name
        
        stl_path = scad_path.replace('.scad', '.stl')
        
        cmd = [
            'openscad',
            '-o', stl_path,
            '--export-format', 'binstl',
            scad_path
        ]
        
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
            logger.error(f"OpenSCAD error: {result.stderr}")
            return jsonify({
                'error': 'OpenSCAD execution failed',
                'details': result.stderr
            }), 500
        
        if not os.path.exists(stl_path):
            logger.error("STL file not generated")
            return jsonify({
                'error': 'STL file not generated'
            }), 500
        
        logger.info(f"STL generated successfully: {stl_path}")
        
        response = send_file(
            stl_path,
            mimetype='application/octet-stream',
            as_attachment=True,
            download_name=f'{letter1}{letter2}_DUET.stl'
        )
        
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

# ==========================================
# 金流和訂單處理
# ==========================================

def generate_check_mac_value(params, hash_key, hash_iv):
    """產生綠界 CheckMacValue"""
    sorted_params = sorted(params.items())
    param_str = '&'.join([f"{k}={v}" for k, v in sorted_params])
    raw_str = f"HashKey={hash_key}&{param_str}&HashIV={hash_iv}"
    encoded_str = urllib.parse.quote_plus(raw_str).lower()
    check_mac = hashlib.sha256(encoded_str.encode('utf-8')).hexdigest().upper()
    logger.info(f"🔐 CheckMacValue 生成: {check_mac[:10]}...")
    return check_mac

def save_order(order_id, order_data):
    """儲存訂單"""
    filepath = os.path.join(ORDERS_DIR, f'{order_id}.json')
    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(order_data, f, ensure_ascii=False, indent=2)
    logger.info(f"✅ 訂單已儲存: {order_id}")

def load_order(order_id):
    """讀取訂單"""
    filepath = os.path.join(ORDERS_DIR, f'{order_id}.json')
    if not os.path.exists(filepath):
        logger.error(f"❌ 訂單不存在: {order_id}")
        return None
    with open(filepath, 'r', encoding='utf-8') as f:
        return json.load(f)

def update_order_status(order_id, status, payment_data=None):
    """更新訂單狀態"""
    order = load_order(order_id)
    if not order:
        return False
    order['status'] = status
    order['updated_at'] = datetime.now().isoformat()
    if payment_data:
        order['payment_data'] = payment_data
    save_order(order_id, order)
    logger.info(f"📝 訂單狀態更新: {order_id} → {status}")
    return True

# ==========================================
# Email 系統
# ==========================================

def send_confirmation_email(order_data):
    """發送付款確認 Email（不含 STL）"""
    try:
        logger.info(f"📧 發送確認 Email: {order_data['orderId']}")
        
        msg = MIMEMultipart()
        msg['From'] = f"{EMAIL_CONFIG['sender_name']} <{EMAIL_CONFIG['sender_email']}>"
        msg['To'] = EMAIL_CONFIG['internal_email']
        msg['Subject'] = f"訂單確認 - {order_data['orderId']}"
        
        html_body = generate_confirmation_email_html(order_data)
        msg.attach(MIMEText(html_body, 'html', 'utf-8'))
        
        with smtplib.SMTP(EMAIL_CONFIG['smtp_server'], EMAIL_CONFIG['smtp_port']) as server:
            server.starttls()
            server.login(EMAIL_CONFIG['sender_email'], EMAIL_CONFIG['sender_password'])
            server.send_message(msg)
        
        logger.info(f"✅ 確認 Email 發送成功")
        return True
        
    except Exception as e:
        logger.error(f"❌ 確認 Email 發送失敗: {str(e)}")
        return False

def send_stl_email(order_data, stl_files):
    """發送帶 STL 的 Email"""
    try:
        logger.info(f"📧 發送 STL Email: {order_data['orderId']}")
        
        msg = MIMEMultipart()
        msg['From'] = f"{EMAIL_CONFIG['sender_name']} <{EMAIL_CONFIG['sender_email']}>"
        msg['To'] = EMAIL_CONFIG['internal_email']
        msg['Subject'] = f"3D 檔案已完成 - {order_data['orderId']}"
        
        html_body = generate_stl_email_html(order_data)
        msg.attach(MIMEText(html_body, 'html', 'utf-8'))
        
        # 附加 STL 檔案
        for stl_path in stl_files:
            if os.path.exists(stl_path):
                attach_file(msg, stl_path)
        
        with smtplib.SMTP(EMAIL_CONFIG['smtp_server'], EMAIL_CONFIG['smtp_port']) as server:
            server.starttls()
            server.login(EMAIL_CONFIG['sender_email'], EMAIL_CONFIG['sender_password'])
            server.send_message(msg)
        
        logger.info(f"✅ STL Email 發送成功")
        return True
        
    except Exception as e:
        logger.error(f"❌ STL Email 發送失敗: {str(e)}")
        return False

def send_admin_alert(order_id, error_message):
    """發送管理員告警"""
    try:
        msg = MIMEMultipart()
        msg['From'] = EMAIL_CONFIG['sender_email']
        msg['To'] = EMAIL_CONFIG['internal_email']
        msg['Subject'] = f"⚠️ STL 生成失敗 - {order_id}"
        
        body = f'''
        <html>
        <body>
            <h2>⚠️ STL 生成失敗</h2>
            <p><strong>訂單編號:</strong> {order_id}</p>
            <p><strong>錯誤訊息:</strong> {error_message}</p>
            <p>已重試 3 次，仍然失敗。</p>
            <p>請手動處理此訂單。</p>
            <p><a href="{request.host_url}api/retry-stl/{order_id}">點擊重試</a></p>
        </body>
        </html>
        '''
        
        msg.attach(MIMEText(body, 'html', 'utf-8'))
        
        with smtplib.SMTP(EMAIL_CONFIG['smtp_server'], EMAIL_CONFIG['smtp_port']) as server:
            server.starttls()
            server.login(EMAIL_CONFIG['sender_email'], EMAIL_CONFIG['sender_password'])
            server.send_message(msg)
        
        logger.info(f"✅ 管理員告警已發送")
        
    except Exception as e:
        logger.error(f"❌ 管理員告警發送失敗: {str(e)}")

def attach_file(msg, filepath):
    """附加檔案到 Email"""
    filename = os.path.basename(filepath)
    with open(filepath, 'rb') as f:
        part = MIMEBase('application', 'octet-stream')
        part.set_payload(f.read())
    encoders.encode_base64(part)
    part.add_header('Content-Disposition', f'attachment; filename="{filename}"')
    msg.attach(part)
    logger.info(f"📎 附加檔案: {filename}")

def generate_confirmation_email_html(order_data):
    """生成確認 Email HTML"""
    items_html = ''
    for idx, item in enumerate(order_data['items'], 1):
        items_html += f'''
        <tr>
            <td>{idx}</td>
            <td>{item['letter1']} + {item['letter2']}</td>
            <td>{item['size']} mm</td>
            <td>{item['quantity']}</td>
            <td>NT$ {item['price'] * item['quantity']:,}</td>
        </tr>
        '''
    
    test_mode_warning = ''
    if order_data.get('testMode'):
        test_mode_warning = '<div style="background: #fff3cd; color: #856404; padding: 15px; border-radius: 5px; margin-bottom: 20px;"><strong>⚠️ 測試訂單</strong></div>'
    
    html = f'''
    <!DOCTYPE html>
    <html>
    <head><meta charset="UTF-8"><style>
        body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
        .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
        .header {{ background: #4CAF50; color: white; padding: 20px; text-align: center; border-radius: 5px; }}
        table {{ width: 100%; border-collapse: collapse; margin: 20px 0; }}
        th, td {{ padding: 10px; border: 1px solid #ddd; text-align: left; }}
        th {{ background: #f5f5f5; }}
    </style></head>
    <body>
        <div class="container">
            <div class="header">
                <h1>✅ 訂單確認</h1>
                <p>訂單編號: {order_data['orderId']}</p>
            </div>
            {test_mode_warning}
            <h2>付款成功！</h2>
            <p>感謝您的訂購，我們已收到您的付款。</p>
            <h3>訂購項目</h3>
            <table>
                <tr>
                    <th>#</th>
                    <th>字母</th>
                    <th>尺寸</th>
                    <th>數量</th>
                    <th>金額</th>
                </tr>
                {items_html}
                <tr>
                    <td colspan="4" style="text-align: right;"><strong>總計:</strong></td>
                    <td><strong>NT$ {order_data['total']:,}</strong></td>
                </tr>
            </table>
            <div style="background: #e3f2fd; padding: 15px; border-radius: 5px; margin: 20px 0;">
                <p><strong>📌 下一步</strong></p>
                <p>我們正在為您製作 3D 檔案，完成後將再次通知您。</p>
                <p>預計時間：5-10 分鐘</p>
            </div>
            <p style="color: #666; font-size: 12px;">此郵件由系統自動發送</p>
        </div>
    </body>
    </html>
    '''
    return html

def generate_stl_email_html(order_data):
    """生成 STL Email HTML"""
    items_html = ''
    for idx, item in enumerate(order_data['items'], 1):
        items_html += f'<li>{item["letter1"]} + {item["letter2"]} ({item["size"]} mm)</li>'
    
    html = f'''
    <!DOCTYPE html>
    <html>
    <head><meta charset="UTF-8"><style>
        body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
        .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
        .header {{ background: #2196F3; color: white; padding: 20px; text-align: center; border-radius: 5px; }}
    </style></head>
    <body>
        <div class="container">
            <div class="header">
                <h1>🎉 3D 檔案已完成</h1>
                <p>訂單編號: {order_data['orderId']}</p>
            </div>
            <h2>檔案製作完成！</h2>
            <p>您訂購的 3D 檔案已製作完成。</p>
            <h3>項目清單</h3>
            <ul>{items_html}</ul>
            <div style="background: #fff3cd; padding: 15px; border-radius: 5px; margin: 20px 0;">
                <p><strong>📎 附件</strong></p>
                <p>STL 檔案已附加在此郵件中，請下載使用。</p>
            </div>
            <p>我們將盡快為您製作實體產品。</p>
            <p style="color: #666; font-size: 12px;">此郵件由系統自動發送</p>
        </div>
    </body>
    </html>
    '''
    return html

# ==========================================
# 金流 API
# ==========================================

@app.route('/api/checkout', methods=['POST'])
def checkout():
    """初始化綠界支付"""
    try:
        data = request.json
        logger.info(f"💳 收到結帳請求: {data.get('orderId')}")
        
        order_id = data['orderId']
        total = data['total']
        items = data['items']
        user_info = data['userInfo']
        return_url = data.get('returnUrl', request.host_url + 'payment-success')
        
        order_data = {
            'orderId': order_id,
            'total': total,
            'items': items,
            'userInfo': user_info,
            'status': 'pending',
            'timestamp': datetime.now().isoformat(),
            'testMode': False
        }
        save_order(order_id, order_data)
        
        payment_params = {
            'MerchantID': ECPAY_CONFIG['MerchantID'],
            'MerchantTradeNo': order_id,
            'MerchantTradeDate': datetime.now().strftime('%Y/%m/%d %H:%M:%S'),
            'PaymentType': 'aio',
            'TotalAmount': str(total),
            'TradeDesc': 'DUET客製墜飾',
            'ItemName': f"客製墜飾 x {len(items)}",
            'ReturnURL': request.host_url.rstrip('/') + '/api/payment/callback',
            'ClientBackURL': return_url,
            'ChoosePayment': 'Credit',
            'EncryptType': '1'
        }
        
        check_mac_value = generate_check_mac_value(
            payment_params, 
            ECPAY_CONFIG['HashKey'], 
            ECPAY_CONFIG['HashIV']
        )
        payment_params['CheckMacValue'] = check_mac_value
        
        form_html = generate_payment_form(payment_params)
        
        logger.info(f"✅ 支付表單已生成: {order_id}")
        
        return jsonify({
            'success': True,
            'paymentFormHTML': form_html,
            'orderId': order_id
        })
        
    except Exception as e:
        logger.error(f"❌ 結帳錯誤: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

def generate_payment_form(params):
    """生成綠界支付表單 HTML"""
    form_fields = ''.join([
        f'<input type="hidden" name="{k}" value="{v}">'
        for k, v in params.items()
    ])
    html = f'''
    <form id="ecpay-form" method="post" action="{ECPAY_CONFIG['PaymentURL']}">
        {form_fields}
    </form>
    '''
    return html

@app.route('/api/payment/callback', methods=['POST'])
def payment_callback():
    """綠界支付回調"""
    try:
        data = request.form.to_dict()
        logger.info(f"📥 收到綠界回調: {data.get('MerchantTradeNo')}")
        
        # 驗證 CheckMacValue
        received_check_mac = data.pop('CheckMacValue', '')
        calculated_check_mac = generate_check_mac_value(
            data, 
            ECPAY_CONFIG['HashKey'], 
            ECPAY_CONFIG['HashIV']
        )
        
        if received_check_mac != calculated_check_mac:
            logger.error(f"❌ CheckMacValue 驗證失敗！")
            return '0|CheckMacValue Error'
        
        logger.info("✅ CheckMacValue 驗證通過")
        
        if data.get('RtnCode') == '1':
            order_id = data['MerchantTradeNo']
            logger.info(f"✅ 訂單 {order_id} 付款成功")
            process_order_after_payment(order_id, data)
            return '1|OK'
        else:
            logger.warning(f"⚠️ 付款失敗: {data.get('RtnMsg')}")
            order_id = data.get('MerchantTradeNo')
            if order_id:
                update_order_status(order_id, 'payment_failed', data)
            return '0|Payment Failed'
            
    except Exception as e:
        logger.error(f"❌ 回調處理錯誤: {str(e)}")
        return '0|Error'

def process_order_after_payment(order_id, payment_data):
    """
    付款成功後處理訂單（新版：使用隊列）
    """
    try:
        logger.info(f"🔄 開始處理訂單: {order_id}")
        
        order = load_order(order_id)
        if not order:
            logger.error(f"❌ 訂單不存在: {order_id}")
            return False
        
        # 1. 更新訂單狀態為已付款
        update_order_status(order_id, 'paid', payment_data)
        
        # 2. 立即發送確認 Email（不含 STL）
        confirmation_sent = send_confirmation_email(order)
        
        if not confirmation_sent:
            logger.warning(f"⚠️ 確認 Email 發送失敗: {order_id}")
        
        # 3. 加入 STL 生成隊列
        add_to_stl_queue(order_id)
        
        logger.info(f"✅ 訂單 {order_id} 初步處理完成，已加入 STL 隊列")
        return True
        
    except Exception as e:
        logger.error(f"❌ 訂單處理錯誤: {str(e)}")
        update_order_status(order_id, 'error')
        return False

@app.route('/api/test-order', methods=['POST'])
def test_order():
    """測試模式：模擬訂單處理"""
    try:
        data = request.json
        logger.info(f"🧪 測試模式訂單: {data.get('orderId')}")
        
        save_order(data['orderId'], data)
        
        # 立即發送確認 Email
        confirmation_sent = send_confirmation_email(data)
        
        if not confirmation_sent:
            return jsonify({
                'success': False,
                'error': 'Email 發送失敗'
            }), 500
        
        # 加入 STL 生成隊列
        add_to_stl_queue(data['orderId'])
        
        update_order_status(data['orderId'], 'test_processing')
        
        return jsonify({
            'success': True,
            'message': '測試訂單已處理，確認 Email 已發送，STL 正在背景生成'
        })
            
    except Exception as e:
        logger.error(f"❌ 測試訂單錯誤: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/process-queue', methods=['POST'])
def trigger_queue_processing():
    """手動觸發隊列處理（可以用 cron job 定時呼叫）"""
    try:
        process_stl_queue()
        return jsonify({
            'success': True,
            'message': '隊列處理已觸發'
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/retry-stl/<order_id>', methods=['GET', 'POST'])
def retry_stl(order_id):
    """手動重試 STL 生成"""
    try:
        logger.info(f"🔄 手動重試 STL 生成: {order_id}")
        
        # 重新加入隊列
        add_to_stl_queue(order_id, retry_count=0)
        
        # 立即處理
        process_stl_queue()
        
        return jsonify({
            'success': True,
            'message': f'訂單 {order_id} 已重新加入隊列'
        })
        
    except Exception as e:
        logger.error(f"❌ 重試失敗: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/payment-success')
def payment_success():
    """支付成功頁面"""
    return '''
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <title>支付成功 - DUET</title>
        <style>
            body {
                font-family: Arial, sans-serif;
                display: flex;
                justify-content: center;
                align-items: center;
                height: 100vh;
                margin: 0;
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            }
            .container {
                background: white;
                padding: 40px;
                border-radius: 15px;
                text-align: center;
                box-shadow: 0 10px 40px rgba(0,0,0,0.2);
            }
            .success-icon { font-size: 60px; color: #4CAF50; margin-bottom: 20px; }
            h1 { color: #333; margin-bottom: 10px; }
            p { color: #666; line-height: 1.6; }
            .btn {
                display: inline-block;
                margin-top: 20px;
                padding: 12px 30px;
                background: #667eea;
                color: white;
                text-decoration: none;
                border-radius: 5px;
            }
        </style>
    </head>
    <body>
        <div class="container">
            <div class="success-icon">✅</div>
            <h1>支付成功！</h1>
            <p>感謝您的訂購！</p>
            <p>確認信已發送至您的信箱。</p>
            <p>3D 檔案將在 5-10 分鐘內完成製作。</p>
            <a href="/" class="btn">返回首頁</a>
        </div>
    </body>
    </html>
    '''

# ==========================================
# 啟動應用
# ==========================================

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    logger.info("🚀 DUET Backend 啟動中...")
    logger.info(f"📧 Email: {EMAIL_CONFIG['sender_email']} → {EMAIL_CONFIG['internal_email']}")
    logger.info(f"💳 綠界: {ECPAY_CONFIG['MerchantID']}")
    logger.info(f"📂 訂單目錄: {ORDERS_DIR}")
    logger.info(f"📋 隊列目錄: {QUEUE_DIR}")
    
    # 啟動背景 Worker
    start_background_worker()
    
    app.run(host='0.0.0.0', port=port, debug=False)
