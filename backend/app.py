"""
DUET Backend - 完整版（使用 Resend Email）
包含：STL 生成、綠界金流、Resend Email、隊列系統
"""

from flask import Flask, request, jsonify, send_file
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
import resend
import threading
import time
import base64

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

# Google Sheets 整合（選用）
try:
    from google.oauth2 import service_account
    from googleapiclient.discovery import build
    GOOGLE_SHEETS_ENABLED = True
except ImportError:
    GOOGLE_SHEETS_ENABLED = False
    logger.warning("⚠️ Google Sheets 模組未安裝，將跳過 Sheets 整合")
logger = logging.getLogger(__name__)

TEMP_DIR = tempfile.gettempdir()
os.makedirs(TEMP_DIR, exist_ok=True)

# ==========================================
# 配置
# ==========================================

# 綠界配置
ECPAY_CONFIG = {
    'MerchantID': '3317971',
    'HashKey': 'MN7lld33ls2A7ACQ',
    'HashIV': 'JsQNlwsz3QtbVKIq',
    'PaymentURL': 'https://payment.ecpay.com.tw/Cashier/AioCheckOut/V5'
}

# Resend Email 配置
RESEND_API_KEY = 're_Vy8zWUJ2_KhUfFBXD5qiPEVPPsLAghgGr'
SENDER_EMAIL = 'onboarding@resend.dev'  # 測試用，之後改成 service@brendonchen.com
SENDER_NAME = 'DUET 客製珠寶'
INTERNAL_EMAIL = 'brendon@brendonchen.com'

# 設定 Resend API Key
resend.api_key = RESEND_API_KEY

# Google Sheets 配置（選用）
GOOGLE_SHEETS_ID = os.environ.get('GOOGLE_SHEETS_ID', '')  # 從環境變數讀取
GOOGLE_CREDENTIALS_JSON = os.environ.get('GOOGLE_CREDENTIALS_JSON', '')  # Service Account JSON

# 目錄配置
ORDERS_DIR = 'orders'
STL_DIR = 'stl_files'
QUEUE_DIR = 'stl_queue'
ORDERS_FILE = os.path.join(ORDERS_DIR, 'orders.json')  # 持久化訂單資料
os.makedirs(ORDERS_DIR, exist_ok=True)
os.makedirs(STL_DIR, exist_ok=True)
os.makedirs(QUEUE_DIR, exist_ok=True)

# ==========================================
# 訂單資料管理
# ==========================================

# 訂單資料（記憶體中）
orders = {}

def load_orders():
    """從檔案載入訂單資料"""
    global orders
    if os.path.exists(ORDERS_FILE):
        try:
            with open(ORDERS_FILE, 'r', encoding='utf-8') as f:
                orders = json.load(f)
            logger.info(f"📂 已載入 {len(orders)} 筆訂單")
        except Exception as e:
            logger.error(f"❌ 載入訂單失敗: {e}")
            orders = {}
    else:
        orders = {}
        logger.info("📂 初始化空訂單資料")

def save_orders():
    """儲存訂單資料到檔案"""
    try:
        with open(ORDERS_FILE, 'w', encoding='utf-8') as f:
            json.dump(orders, f, ensure_ascii=False, indent=2)
        logger.info(f"💾 已儲存 {len(orders)} 筆訂單")
    except Exception as e:
        logger.error(f"❌ 儲存訂單失敗: {e}")

def save_order(order_id, order_data):
    """儲存單筆訂單"""
    orders[order_id] = order_data
    save_orders()
    logger.info(f"✅ 訂單已儲存: {order_id}")

def get_order(order_id):
    """取得訂單資料"""
    return orders.get(order_id)

# ==========================================
# Google Sheets 整合
# ==========================================

def save_to_google_sheets(order_data):
    """儲存訂單到 Google Sheets"""
    if not GOOGLE_SHEETS_ENABLED or not GOOGLE_SHEETS_ID or not GOOGLE_CREDENTIALS_JSON:
        logger.warning("⚠️ Google Sheets 未啟用，跳過")
        return
    
    try:
        # 載入憑證
        import tempfile
        creds_file = tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.json')
        creds_file.write(GOOGLE_CREDENTIALS_JSON)
        creds_file.close()
        
        creds = service_account.Credentials.from_service_account_file(
            creds_file.name,
            scopes=['https://www.googleapis.com/auth/spreadsheets']
        )
        service = build('sheets', 'v4', credentials=creds)
        
        # 準備資料行
        items = order_data.get('items', [])
        item1 = json.dumps(items[0], ensure_ascii=False) if len(items) > 0 else ''
        item2 = json.dumps(items[1], ensure_ascii=False) if len(items) > 1 else ''
        item3 = json.dumps(items[2], ensure_ascii=False) if len(items) > 2 else ''
        
        row = [
            order_data.get('orderId', ''),
            order_data.get('userInfo', {}).get('name', ''),
            order_data.get('userInfo', {}).get('email', ''),
            order_data.get('userInfo', {}).get('phone', ''),
            item1,
            item2,
            item3,
            order_data.get('total', 0),
            datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            order_data.get('status', 'pending')
        ]
        
        # 寫入 Google Sheets
        service.spreadsheets().values().append(
            spreadsheetId=GOOGLE_SHEETS_ID,
            range='訂單!A:J',
            valueInputOption='RAW',
            body={'values': [row]}
        ).execute()
        
        logger.info(f"📊 已儲存到 Google Sheets: {order_data.get('orderId')}")
        
        # 清理臨時檔案
        os.unlink(creds_file.name)
        
    except Exception as e:
        logger.error(f"❌ Google Sheets 儲存失敗: {e}")

# ==========================================
# 隊列系統
# ==========================================

def add_to_stl_queue(order_id):
    """加入 STL 生成隊列"""
    queue_item = {
        'order_id': order_id,
        'added_at': datetime.now().isoformat(),
        'retry_count': 0,
        'status': 'pending'
    }
    
    queue_file = os.path.join(QUEUE_DIR, f'{order_id}.json')
    with open(queue_file, 'w', encoding='utf-8') as f:
        json.dump(queue_item, f, ensure_ascii=False, indent=2)
    
    logger.info(f"✅ 訂單 {order_id} 已加入 STL 隊列")

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
                except:
                    pass
    except:
        pass
    return items

def remove_from_queue(queue_file):
    """從隊列移除"""
    try:
        os.unlink(queue_file)
        logger.info(f"✅ 已從隊列移除")
    except:
        pass

def process_stl_queue():
    """處理 STL 隊列"""
    items = get_pending_queue_items()
    
    if not items:
        return
    
    logger.info(f"📋 隊列中有 {len(items)} 個待處理項目")
    
    # 每次處理一個
    queue_file, item = items[0]
    order_id = item['order_id']
    retry_count = item.get('retry_count', 0)
    
    logger.info(f"🔨 處理訂單: {order_id}")
    
    try:
        success = generate_and_send_stl(order_id)
        
        if success:
            remove_from_queue(queue_file)
            update_order_status(order_id, 'completed')
            logger.info(f"✅ 訂單 {order_id} 處理完成")
        else:
            if retry_count < 3:
                item['retry_count'] = retry_count + 1
                with open(queue_file, 'w', encoding='utf-8') as f:
                    json.dump(item, f, ensure_ascii=False, indent=2)
                logger.warning(f"⚠️ 訂單 {order_id} 失敗，將重試 ({retry_count + 1}/3)")
            else:
                item['status'] = 'failed'
                with open(queue_file, 'w', encoding='utf-8') as f:
                    json.dump(item, f, ensure_ascii=False, indent=2)
                update_order_status(order_id, 'stl_failed')
                logger.error(f"❌ 訂單 {order_id} 重試 3 次後失敗")
                
    except Exception as e:
        logger.error(f"❌ 處理錯誤: {str(e)}")

def stl_queue_worker():
    """背景 Worker"""
    logger.info("🚀 STL Queue Worker 已啟動")
    
    while True:
        try:
            process_stl_queue()
        except Exception as e:
            logger.error(f"Worker 錯誤: {str(e)}")
        
        time.sleep(60)

def start_background_worker():
    """啟動背景 Worker（使用文件鎖確保只啟動一次）"""
    import fcntl
    lock_file = '/tmp/duet_worker.lock'
    
    try:
        # 嘗試取得鎖
        lock_fd = open(lock_file, 'w')
        fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        
        # 成功取得鎖，啟動 Worker
        worker_thread = threading.Thread(target=stl_queue_worker, daemon=True)
        worker_thread.start()
        logger.info("✅ 背景 Worker 已啟動（已取得鎖）")
        
        # 保持文件打開以維持鎖
        app._worker_lock_fd = lock_fd
        
    except IOError:
        # 鎖已被其他進程持有
        logger.info("⏸️ 背景 Worker 已在其他進程中運行，跳過啟動")

# ==========================================
# STL 生成
# ==========================================

def generate_stl_for_item(item):
    """生成 STL"""
    try:
        logger.info(f"🔨 生成 STL: {item['letter1']}{item['letter2']}")
        
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
        
        scad_content = generate_scad_script(**params)
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.scad', delete=False) as scad_file:
            scad_file.write(scad_content)
            scad_path = scad_file.name
        
        stl_path = scad_path.replace('.scad', '.stl')
        
        cmd = ['openscad', '-o', stl_path, '--export-format', 'binstl', scad_path]
        
        env = os.environ.copy()
        env['DISPLAY'] = ':99'
        
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=180, env=env)
        
        try:
            os.unlink(scad_path)
        except:
            pass
        
        if result.returncode != 0 or not os.path.exists(stl_path):
            logger.error(f"❌ STL 生成失敗")
            return None
        
        final_path = os.path.join(STL_DIR, f"{item['id']}.stl")
        import shutil
        shutil.copy(stl_path, final_path)
        
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
    """生成所有 STL 並發送內部 Email-2"""
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
                return False
        
        # 發送內部 Email-2（帶 STL）
        email_sent = send_internal_stl_email(order, stl_files)
        
        return email_sent
        
    except Exception as e:
        logger.error(f"❌ generate_and_send_stl 錯誤: {str(e)}")
        return False

# ==========================================
# 訂單管理
# ==========================================

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
    logger.info(f"📝 訂單狀態: {order_id} → {status}")
    return True

# ==========================================
# Email 系統（使用 Resend）
# ==========================================

def send_customer_confirmation_email(order_data):
    """Email 1: 給顧客的確認 Email"""
    try:
        customer_email = order_data['userInfo']['email']
        logger.info(f"📧 發送顧客確認 Email: {customer_email}")
        
        html = generate_customer_email_html(order_data)
        
        params = {
            "from": f"{SENDER_NAME} <{SENDER_EMAIL}>",
            "to": [customer_email],
            "subject": f"訂單確認 - {order_data['orderId']}",
            "html": html
        }
        
        email = resend.Emails.send(params)
        logger.info(f"✅ 顧客確認 Email 已發送: {email}")
        return True
        
    except Exception as e:
        logger.error(f"❌ 顧客 Email 發送失敗: {str(e)}")
        return False

def send_internal_order_email(order_data):
    """Email 2: 給內部的訂單通知（無 STL）"""
    try:
        logger.info(f"📧 發送內部訂單通知")
        
        html = generate_internal_order_email_html(order_data)
        
        params = {
            "from": f"{SENDER_NAME} <{SENDER_EMAIL}>",
            "to": [INTERNAL_EMAIL],
            "subject": f"新訂單 - {order_data['orderId']}",
            "html": html
        }
        
        email = resend.Emails.send(params)
        logger.info(f"✅ 內部訂單 Email 已發送: {email}")
        return True
        
    except Exception as e:
        logger.error(f"❌ 內部訂單 Email 發送失敗: {str(e)}")
        return False

def send_internal_stl_email(order_data, stl_files):
    """Email 3: 給內部的 STL 完成通知（帶 STL）"""
    try:
        logger.info(f"📧 發送內部 STL Email")
        
        html = generate_internal_stl_email_html(order_data)
        
        # 準備附件
        attachments = []
        for stl_path in stl_files:
            if os.path.exists(stl_path):
                filename = os.path.basename(stl_path)
                with open(stl_path, 'rb') as f:
                    content = base64.b64encode(f.read()).decode()
                    attachments.append({
                        "filename": filename,
                        "content": content
                    })
                logger.info(f"📎 附加: {filename}")
        
        params = {
            "from": f"{SENDER_NAME} <{SENDER_EMAIL}>",
            "to": [INTERNAL_EMAIL],
            "subject": f"STL 已完成 - {order_data['orderId']}",
            "html": html,
            "attachments": attachments
        }
        
        email = resend.Emails.send(params)
        logger.info(f"✅ 內部 STL Email 已發送: {email}")
        return True
        
    except Exception as e:
        logger.error(f"❌ 內部 STL Email 發送失敗: {str(e)}")
        return False

# ==========================================
# Email HTML 模板
# ==========================================

def generate_customer_email_html(order_data):
    """顧客確認 Email HTML"""
    items_html = ''
    for idx, item in enumerate(order_data['items'], 1):
        items_html += f'''
        <tr>
            <td>{idx}</td>
            <td>{item['letter1']} + {item['letter2']}</td>
            <td>{item.get('font1', 'N/A')} + {item.get('font2', 'N/A')}</td>
            <td>{item.get('size', 'N/A')} mm</td>
            <td>{item.get('material', 'N/A')}</td>
            <td>{item.get('quantity', 1)}</td>
        </tr>
        '''
    
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
            <p>親愛的 {order_data['userInfo']['name']}，</p>
            <p>感謝您的訂購！我們已收到您的訂單。</p>
            <h3>訂購項目</h3>
            <table>
                <tr>
                    <th>#</th>
                    <th>字母</th>
                    <th>字體</th>
                    <th>尺寸</th>
                    <th>材質</th>
                    <th>數量</th>
                </tr>
                {items_html}
            </table>
            <p><strong>訂單金額：NT$ {order_data['total']:,}</strong></p>
            <p>我們將盡快為您製作實體產品。</p>
            <p>DUET 客製珠寶 敬上</p>
            <p style="color: #666; font-size: 12px;">此郵件由系統自動發送</p>
        </div>
    </body>
    </html>
    '''
    return html

def generate_internal_order_email_html(order_data):
    """內部訂單通知 Email HTML"""
    items_html = ''
    for idx, item in enumerate(order_data['items'], 1):
        bbox1 = item.get('letter1BBox', {})
        bbox2 = item.get('letter2BBox', {})
        items_html += f'''
        <div style="border: 1px solid #ddd; padding: 15px; margin: 10px 0; border-radius: 5px;">
            <h3>項目 {idx}</h3>
            <p><strong>字母：</strong>{item['letter1']} + {item['letter2']}</p>
            <p><strong>字體：</strong>{item.get('font1', 'N/A')} + {item.get('font2', 'N/A')}</p>
            <p><strong>尺寸：</strong>{item.get('size', 'N/A')} mm</p>
            <p><strong>材質：</strong>{item.get('material', 'N/A')}</p>
            <details>
                <summary style="cursor: pointer; color: #666;">技術參數</summary>
                <pre style="background: #f5f5f5; padding: 10px; font-size: 12px;">
Letter1 BBox: W={bbox1.get('width', 0):.3f}, H={bbox1.get('height', 0):.3f}, D={bbox1.get('depth', 0):.3f}
Letter2 BBox: W={bbox2.get('width', 0):.3f}, H={bbox2.get('height', 0):.3f}, D={bbox2.get('depth', 0):.3f}
Bail: X={item.get('bailAbsoluteX', 0):.3f}, Y={item.get('bailAbsoluteY', 0):.3f}, Z={item.get('bailAbsoluteZ', 0):.3f}
                </pre>
            </details>
        </div>
        '''
    
    test_warning = ''
    if order_data.get('testMode'):
        test_warning = '<div style="background: #fff3cd; padding: 15px; margin: 10px 0;">⚠️ 測試訂單</div>'
    
    html = f'''
    <!DOCTYPE html>
    <html>
    <head><meta charset="UTF-8"></head>
    <body style="font-family: Arial, sans-serif;">
        <div style="max-width: 800px; margin: 0 auto; padding: 20px;">
            <h1 style="background: #2c3e50; color: white; padding: 20px; text-align: center;">
                🎉 新訂單通知
            </h1>
            {test_warning}
            <h2>訂單資訊</h2>
            <p><strong>訂單編號：</strong>{order_data['orderId']}</p>
            <p><strong>訂單時間：</strong>{order_data.get('timestamp', 'N/A')}</p>
            <p><strong>訂單金額：</strong>NT$ {order_data['total']:,}</p>
            <h2>👤 顧客資訊</h2>
            <p><strong>姓名：</strong>{order_data['userInfo']['name']}</p>
            <p><strong>Email：</strong>{order_data['userInfo']['email']}</p>
            <p><strong>電話：</strong>{order_data['userInfo']['phone']}</p>
            <h2>🎁 訂購項目</h2>
            {items_html}
            <p style="background: #e3f2fd; padding: 15px; margin: 20px 0;">
                ⏳ STL 檔案製作中...
            </p>
        </div>
    </body>
    </html>
    '''
    return html

def generate_internal_stl_email_html(order_data):
    """內部 STL 完成 Email HTML"""
    items_list = '<ul>'
    for item in order_data['items']:
        items_list += f'<li>{item["letter1"]} + {item["letter2"]} ({item.get("size", "N/A")} mm)</li>'
    items_list += '</ul>'
    
    html = f'''
    <!DOCTYPE html>
    <html>
    <head><meta charset="UTF-8"></head>
    <body style="font-family: Arial, sans-serif;">
        <div style="max-width: 600px; margin: 0 auto; padding: 20px;">
            <h1 style="background: #2196F3; color: white; padding: 20px; text-align: center;">
                ✅ STL 檔案已完成
            </h1>
            <p><strong>訂單編號：</strong>{order_data['orderId']}</p>
            <h2>📋 項目清單</h2>
            {items_list}
            <div style="background: #fff3cd; padding: 15px; margin: 20px 0;">
                <p><strong>📎 附件</strong></p>
                <p>STL 檔案已附加在此郵件中。</p>
            </div>
        </div>
    </body>
    </html>
    '''
    return html

# ==========================================
# 原有的 STL 生成端點（保留）
# ==========================================

@app.route('/health', methods=['GET'])
def health_check():
    try:
        result = subprocess.run(['which', 'openscad'], capture_output=True, text=True, timeout=5)
        if result.returncode == 0:
            openscad_path = result.stdout.strip()
            version_result = subprocess.run(['openscad', '--version'], 
                                          capture_output=True, text=True, timeout=5,
                                          env={'DISPLAY': ':99'})
            version_info = version_result.stdout.strip() or version_result.stderr.strip() or "Installed"
            openscad_status = f"{openscad_path} - {version_info}"
        else:
            openscad_status = "Not found"
    except Exception as e:
        openscad_status = f"Error: {str(e)}"
    
    queue_items = get_pending_queue_items()
    
    return jsonify({
        'status': 'healthy',
        'openscad': openscad_status,
        'payment_enabled': True,
        'email_enabled': True,
        'email_service': 'Resend',
        'queue_system': True,
        'pending_stl_jobs': len(queue_items)
    })

def get_available_fonts():
    try:
        result = subprocess.run(['fc-list'], capture_output=True, text=True, timeout=10)
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
    except:
        return set()

def validate_font(font_name):
    available_fonts = get_available_fonts()
    if not available_fonts:
        raise ValueError("Cannot get system fonts")
    if font_name not in available_fonts:
        raise ValueError(f"Font '{font_name}' not found")
    return font_name

@app.route('/list-fonts', methods=['GET'])
def list_fonts():
    try:
        result = subprocess.run(['fc-list'], capture_output=True, text=True, timeout=10)
        if result.returncode != 0:
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
        return jsonify({'fonts': sorted_fonts, 'total': len(sorted_fonts)})
    except:
        return jsonify({'error': 'Internal server error'}), 500

@app.route('/generate', methods=['POST'])
def generate_stl():
    """原有的即時 STL 生成端點"""
    try:
        data = request.json
        
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
            letter1=letter1, letter2=letter2, font1=font1, font2=font2, size=size,
            bailRelativeX=bailRelativeX, bailRelativeY=bailRelativeY, bailRelativeZ=bailRelativeZ,
            bailRotation=bailRotation, bailAbsoluteX=bailAbsoluteX, bailAbsoluteY=bailAbsoluteY,
            bailAbsoluteZ=bailAbsoluteZ, letter1Width=letter1Width, letter1Height=letter1Height,
            letter1Depth=letter1Depth, letter1OffsetX=letter1OffsetX, letter1OffsetY=letter1OffsetY,
            letter1OffsetZ=letter1OffsetZ, letter2Width=letter2Width, letter2Height=letter2Height,
            letter2Depth=letter2Depth, letter2OffsetX=letter2OffsetX, letter2OffsetY=letter2OffsetY,
            letter2OffsetZ=letter2OffsetZ
        )
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.scad', delete=False) as scad_file:
            scad_file.write(scad_content)
            scad_path = scad_file.name
        
        stl_path = scad_path.replace('.scad', '.stl')
        cmd = ['openscad', '-o', stl_path, '--export-format', 'binstl', scad_path]
        env = os.environ.copy()
        env['DISPLAY'] = ':99'
        
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=180, env=env)
        
        if result.returncode != 0:
            return jsonify({'error': 'OpenSCAD execution failed'}), 500
        
        if not os.path.exists(stl_path):
            return jsonify({'error': 'STL file not generated'}), 500
        
        response = send_file(stl_path, mimetype='application/octet-stream',
                           as_attachment=True, download_name=f'{letter1}{letter2}_DUET.stl')
        
        @response.call_on_close
        def cleanup():
            try:
                os.unlink(scad_path)
                os.unlink(stl_path)
            except:
                pass
        
        return response
    except Exception as e:
        return jsonify({'error': 'Internal server error', 'details': str(e)}), 500

# ==========================================
# 金流 API
# ==========================================

def prepare_custom_fields(order_data):
    """準備綠界 CustomField（訂單備份）"""
    try:
        user_info = order_data.get('userInfo', {})
        items = order_data.get('items', [])
        
        # CustomField1: 關鍵資訊 (~60字)
        field1 = json.dumps({
            "O": order_data.get('orderId', ''),
            "N": user_info.get('name', ''),
            "E": user_info.get('email', ''),
            "P": user_info.get('phone', ''),
            "I": len(items),
            "T": order_data.get('total', 0)
        }, ensure_ascii=False)[:200]
        
        # CustomField2-4: 各物件參數（每個~100字）
        def compress_item(item):
            return json.dumps({
                "L1": item.get('letter1', ''),
                "L2": item.get('letter2', ''),
                "F1": item.get('font1', ''),
                "F2": item.get('font2', ''),
                "S": item.get('size', 15),
                "M": item.get('material', '金'),
                # ✅ 使用 bailRelative（相對向量），不是 bailAbsolute
                "BX": item.get('bailRelativeX', 0),
                "BY": item.get('bailRelativeY', 0),
                "BZ": item.get('bailRelativeZ', 0)
            }, ensure_ascii=False)[:200]
        
        field2 = compress_item(items[0]) if len(items) > 0 else ''
        field3 = compress_item(items[1]) if len(items) > 1 else ''
        field4 = compress_item(items[2]) if len(items) > 2 else ''
        
        return {
            'CustomField1': field1,
            'CustomField2': field2,
            'CustomField3': field3,
            'CustomField4': field4
        }
    except Exception as e:
        logger.error(f"❌ 準備 CustomField 失敗: {e}")
        return {}

def generate_check_mac_value(params, hash_key, hash_iv):
    """產生綠界 CheckMacValue"""
    sorted_params = sorted(params.items())
    param_str = '&'.join([f"{k}={v}" for k, v in sorted_params])
    raw_str = f"HashKey={hash_key}&{param_str}&HashIV={hash_iv}"
    encoded_str = urllib.parse.quote_plus(raw_str).lower()
    check_mac = hashlib.sha256(encoded_str.encode('utf-8')).hexdigest().upper()
    return check_mac

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
        
        # 準備 CustomField（訂單備份）
        custom_fields = prepare_custom_fields(order_data)
        
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
            'EncryptType': '1',
            **custom_fields  # 加入 CustomField
        }
        
        check_mac_value = generate_check_mac_value(payment_params, 
                                                   ECPAY_CONFIG['HashKey'], 
                                                   ECPAY_CONFIG['HashIV'])
        payment_params['CheckMacValue'] = check_mac_value
        
        form_fields = ''.join([f'<input type="hidden" name="{k}" value="{v}">' 
                              for k, v in payment_params.items()])
        form_html = f'<form id="ecpay-form" method="post" action="{ECPAY_CONFIG["PaymentURL"]}">{form_fields}</form>'
        
        logger.info(f"✅ 綠界表單已生成，包含 CustomField 備份")
        
        return jsonify({'success': True, 'paymentFormHTML': form_html, 'orderId': order_id})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/payment/callback', methods=['POST'])
def payment_callback():
    """綠界支付回調"""
    try:
        data = request.form.to_dict()
        logger.info(f"📥 收到綠界回調: {data.get('MerchantTradeNo')}")
        
        received_check_mac = data.pop('CheckMacValue', '')
        calculated_check_mac = generate_check_mac_value(data, 
                                                       ECPAY_CONFIG['HashKey'], 
                                                       ECPAY_CONFIG['HashIV'])
        
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
            order_id = data.get('MerchantTradeNo')
            if order_id:
                update_order_status(order_id, 'payment_failed', data)
            return '0|Payment Failed'
    except Exception as e:
        logger.error(f"❌ 回調處理錯誤: {str(e)}")
        return '0|Error'

def process_order_after_payment(order_id, payment_data):
    """付款成功後處理訂單（非同步）"""
    try:
        order = get_order(order_id)
        if not order:
            logger.error(f"❌ 找不到訂單: {order_id}")
            return False
        
        # 1. 立即更新訂單狀態（同步）
        update_order_status(order_id, 'paid', payment_data)
        
        # 2. 非同步處理（不阻塞綠界回調）
        def async_tasks():
            try:
                # 發送顧客確認 Email
                send_customer_confirmation_email(order)
                logger.info(f"✅ Email 1 已發送: {order_id}")
                
                # ✅ 移除第二封內部訂單通知（改用綠界 CustomField 備份）
                # send_internal_order_email(order)  # ← 不再需要
                
                # 儲存到 Google Sheets
                save_to_google_sheets(order)
                
                # 加入 STL 生成隊列
                add_to_stl_queue(order_id)
                
            except Exception as e:
                logger.error(f"❌ 非同步任務錯誤: {e}")
        
        # 啟動背景線程
        threading.Thread(target=async_tasks, daemon=True).start()
        
        logger.info(f"✅ 訂單 {order_id} 已加入處理隊列")
        return True
    except Exception as e:
        logger.error(f"❌ 訂單處理錯誤: {str(e)}")
        return False

@app.route('/api/test-order', methods=['POST'])
def test_order():
    """測試模式：模擬訂單處理（非同步）"""
    try:
        data = request.json
        order_id = data.get('orderId')
        logger.info(f"🧪 測試模式訂單: {order_id}")
        
        # 立即儲存訂單（同步）
        save_order(order_id, data)
        
        # 更新訂單狀態
        update_order_status(order_id, 'test_processing')
        
        # 非同步處理（不阻塞前端）
        def async_tasks():
            try:
                # 發送顧客確認 Email
                send_customer_confirmation_email(data)
                logger.info(f"✅ Email 1 已發送: {order_id}")
                
                # ✅ 移除第二封內部訂單通知（改用綠界 CustomField 備份）
                # send_internal_order_email(data)  # ← 不再需要
                
                # 儲存到 Google Sheets
                save_to_google_sheets(data)
                
                # 加入 STL 生成隊列
                add_to_stl_queue(order_id)
                
            except Exception as e:
                logger.error(f"❌ 非同步任務錯誤: {e}")
        
        # 啟動背景線程
        threading.Thread(target=async_tasks, daemon=True).start()
        
        # 立即返回（前端不等待）
        return jsonify({
            'success': True,
            'message': '測試訂單已處理，Email 已發送，STL 正在背景生成'
        })
            
    except Exception as e:
        logger.error(f"❌ 測試訂單錯誤: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/payment-success')
def payment_success():
    """支付成功頁面"""
    return '''<!DOCTYPE html><html><head><meta charset="UTF-8"><title>支付成功 - DUET</title>
    <style>body{font-family:Arial;display:flex;justify-content:center;align-items:center;height:100vh;
    margin:0;background:linear-gradient(135deg,#667eea 0%,#764ba2 100%)}.container{background:white;
    padding:40px;border-radius:15px;text-align:center;box-shadow:0 10px 40px rgba(0,0,0,0.2)}
    .success-icon{font-size:60px;color:#4CAF50;margin-bottom:20px}h1{color:#333;margin-bottom:10px}
    p{color:#666;line-height:1.6}.btn{display:inline-block;margin-top:20px;padding:12px 30px;
    background:#667eea;color:white;text-decoration:none;border-radius:5px}</style></head>
    <body><div class="container"><div class="success-icon">✅</div><h1>支付成功！</h1>
    <p>感謝您的訂購！</p><p>確認信已發送至您的信箱。</p><p>我們將盡快為您製作產品。</p>
    <a href="/" class="btn">返回首頁</a></div></body></html>'''

# ==========================================
# 初始化（Gunicorn 會執行這裡）
# ==========================================

logger.info("🚀 DUET Backend 初始化中...")
logger.info(f"📧 Email 服務: Resend")
logger.info(f"📧 發件人: {SENDER_EMAIL}")
logger.info(f"📧 內部收件: {INTERNAL_EMAIL}")
logger.info(f"💳 綠界: {ECPAY_CONFIG['MerchantID']}")

# 載入訂單資料
load_orders()

# 啟動背景 Worker
start_background_worker()

# ==========================================
# 本地開發用
# ==========================================

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
