"""
DUET Backend - 整合版
包含：STL 生成、綠界金流、Email 發送
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

# 綠界配置（正式環境）
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
    'sender_password': 'daqd awju eodn dwpa',
    'sender_name': 'DUET 客製珠寶',
    'internal_email': 'brendon@brendonchen.com'
}

# 訂單儲存目錄
ORDERS_DIR = 'orders'
STL_DIR = 'stl_files'
os.makedirs(ORDERS_DIR, exist_ok=True)
os.makedirs(STL_DIR, exist_ok=True)

# ==========================================
# 原有功能：STL 生成
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
    
    return jsonify({
        'status': 'healthy',
        'openscad': openscad_status,
        'temp_dir': TEMP_DIR,
        'payment_enabled': True,
        'email_enabled': True
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
    try:
        data = request.json
        logger.info(f"Received request: {data}")
        
        letter1 = data.get('letter1', 'D')
        letter2 = data.get('letter2', 'T')
        font1 = data.get('font1', 'Roboto')
        font2 = data.get('font2', 'Roboto')
        size = data.get('size', 20)
        
        # Support multiple parameter formats
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
        
        logger.info(f"Bail params: X={bailRelativeX}, Y={bailRelativeY}, Z={bailRelativeZ}, Rotation={bailRotation}")
        
        bailAbsoluteX = data.get('bailAbsoluteX', 0)
        bailAbsoluteY = data.get('bailAbsoluteY', 0)
        bailAbsoluteZ = data.get('bailAbsoluteZ', 0)
        
        logger.info(f"🔍 Bail absolute position: X={bailAbsoluteX}, Y={bailAbsoluteY}, Z={bailAbsoluteZ}")
        
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
        
        logger.info(f"Letter1 BBox: W={letter1Width}, H={letter1Height}, D={letter1Depth}")
        logger.info(f"Letter2 BBox: W={letter2Width}, H={letter2Height}, D={letter2Depth}")
        
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
        
        logger.info(f"SCAD file: {scad_path}")
        logger.info(f"STL file: {stl_path}")
        
        cmd = [
            'openscad',
            '-o', stl_path,
            '--export-format', 'binstl',
            scad_path
        ]
        
        logger.info(f"Running command: {' '.join(cmd)}")
        
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
# 新功能：金流和 Email
# ==========================================

def generate_check_mac_value(params, hash_key, hash_iv):
    """產生綠界 CheckMacValue - 安全關鍵"""
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

def send_order_email(order_data, stl_files=None):
    """發送訂單通知 Email"""
    try:
        logger.info(f"📧 準備發送訂單 Email: {order_data['orderId']}")
        
        msg = MIMEMultipart()
        msg['From'] = f"{EMAIL_CONFIG['sender_name']} <{EMAIL_CONFIG['sender_email']}>"
        msg['To'] = EMAIL_CONFIG['internal_email']
        msg['Subject'] = f"新訂單 - {order_data['orderId']}"
        
        html_body = generate_order_email_html(order_data)
        msg.attach(MIMEText(html_body, 'html', 'utf-8'))
        
        if stl_files:
            for stl_path in stl_files:
                if os.path.exists(stl_path):
                    attach_file(msg, stl_path)
        
        with smtplib.SMTP(EMAIL_CONFIG['smtp_server'], EMAIL_CONFIG['smtp_port']) as server:
            server.starttls()
            server.login(EMAIL_CONFIG['sender_email'], EMAIL_CONFIG['sender_password'])
            server.send_message(msg)
        
        logger.info(f"✅ Email 發送成功: {order_data['orderId']}")
        return True
        
    except Exception as e:
        logger.error(f"❌ Email 發送失敗: {str(e)}")
        return False

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

def generate_order_email_html(order_data):
    """生成訂單 Email HTML"""
    items_html = ''
    for idx, item in enumerate(order_data['items'], 1):
        items_html += f'''
        <div style="border: 1px solid #ddd; padding: 15px; margin: 10px 0; border-radius: 5px;">
            <h3>項目 {idx}</h3>
            <table style="width: 100%;">
                <tr><td><strong>字母:</strong></td><td>{item['letter1']} + {item['letter2']}</td></tr>
                <tr><td><strong>字體:</strong></td><td>{item['font1']} + {item['font2']}</td></tr>
                <tr><td><strong>尺寸:</strong></td><td>{item['size']} mm</td></tr>
                <tr><td><strong>材質:</strong></td><td>{item['material']}</td></tr>
                <tr><td><strong>數量:</strong></td><td>{item['quantity']}</td></tr>
                <tr><td><strong>小計:</strong></td><td>NT$ {item['price'] * item['quantity']:,}</td></tr>
            </table>
        </div>
        '''
    
    test_mode_warning = ''
    if order_data.get('testMode'):
        test_mode_warning = '''
        <div style="background: #fff3cd; color: #856404; padding: 15px; border-radius: 5px; margin-bottom: 20px;">
            <strong>⚠️ 測試訂單</strong><br>
            此訂單為測試模式產生，未經過真實金流。
        </div>
        '''
    
    html = f'''
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <style>
            body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
            .container {{ max-width: 800px; margin: 0 auto; padding: 20px; }}
            .header {{ background: #2c3e50; color: white; padding: 20px; text-align: center; border-radius: 5px; }}
            table {{ width: 100%; border-collapse: collapse; }}
            td {{ padding: 8px; }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1>🎉 新訂單通知</h1>
                <p>訂單編號: {order_data['orderId']}</p>
            </div>
            <div style="padding: 20px;">
                {test_mode_warning}
                <h2>📋 訂單資訊</h2>
                <table>
                    <tr><td><strong>訂單時間:</strong></td><td>{order_data.get('timestamp', datetime.now().isoformat())}</td></tr>
                    <tr><td><strong>訂單金額:</strong></td><td>NT$ {order_data['total']:,}</td></tr>
                    <tr><td><strong>支付狀態:</strong></td><td>{order_data.get('status', '處理中')}</td></tr>
                </table>
                <h2>👤 客戶資訊</h2>
                <table>
                    <tr><td><strong>姓名:</strong></td><td>{order_data['userInfo']['name']}</td></tr>
                    <tr><td><strong>Email:</strong></td><td>{order_data['userInfo']['email']}</td></tr>
                    <tr><td><strong>電話:</strong></td><td>{order_data['userInfo']['phone']}</td></tr>
                </table>
                <h2>🎁 訂購項目</h2>
                {items_html}
                <hr style="margin: 30px 0;">
                <p style="color: #666; font-size: 14px;">
                    📎 STL 檔案已附加在此郵件中（如果有的話）<br>
                    此郵件由系統自動發送
                </p>
            </div>
        </div>
    </body>
    </html>
    '''
    return html

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
    """綠界支付回調 - 安全關鍵"""
    try:
        data = request.form.to_dict()
        logger.info(f"📥 收到綠界回調: {data.get('MerchantTradeNo')}")
        
        # ⚠️ 安全驗證：CheckMacValue
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
    """付款成功後處理訂單"""
    try:
        logger.info(f"🔄 開始處理訂單: {order_id}")
        order = load_order(order_id)
        if not order:
            logger.error(f"❌ 訂單不存在: {order_id}")
            return False
        
        update_order_status(order_id, 'paid', payment_data)
        
        # TODO: 生成 STL（可以調用 /generate 端點）
        stl_files = []
        
        email_sent = send_order_email(order, stl_files)
        
        if email_sent:
            update_order_status(order_id, 'completed')
            logger.info(f"✅ 訂單處理完成: {order_id}")
        else:
            update_order_status(order_id, 'email_failed')
            logger.warning(f"⚠️ Email 發送失敗: {order_id}")
        
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
        email_sent = send_order_email(data, [])
        
        if email_sent:
            update_order_status(data['orderId'], 'test_completed')
            return jsonify({
                'success': True,
                'message': '測試訂單已處理，Email 已發送'
            })
        else:
            return jsonify({
                'success': False,
                'error': 'Email 發送失敗'
            }), 500
            
    except Exception as e:
        logger.error(f"❌ 測試訂單錯誤: {str(e)}")
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
                transition: background 0.3s;
            }
            .btn:hover { background: #5568d3; }
        </style>
    </head>
    <body>
        <div class="container">
            <div class="success-icon">✅</div>
            <h1>支付成功！</h1>
            <p>感謝您的訂購！</p>
            <p>我們已收到您的訂單，將盡快為您處理。</p>
            <p>訂單確認信已發送至您的信箱。</p>
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
    app.run(host='0.0.0.0', port=port, debug=False)
