"""
DUET Backend - 綠界金流整合
包含：金流串接、Email 發送、訂單處理
"""

from flask import Flask, request, jsonify, redirect, render_template_string
from flask_cors import CORS
import hashlib
import urllib.parse
from datetime import datetime
import json
import os
import logging
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders

# 設定日誌
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

app = Flask(__name__)
CORS(app)

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
# 輔助函數
# ==========================================

def generate_check_mac_value(params, hash_key, hash_iv):
    """
    產生綠界 CheckMacValue
    ⚠️ 安全關鍵：驗證支付真實性
    """
    # 1. 排序參數
    sorted_params = sorted(params.items())
    
    # 2. 組成字串
    param_str = '&'.join([f"{k}={v}" for k, v in sorted_params])
    
    # 3. 加上 HashKey 和 HashIV
    raw_str = f"HashKey={hash_key}&{param_str}&HashIV={hash_iv}"
    
    # 4. URL encode
    encoded_str = urllib.parse.quote_plus(raw_str).lower()
    
    # 5. SHA256 雜湊
    check_mac = hashlib.sha256(encoded_str.encode('utf-8')).hexdigest().upper()
    
    logger.info(f"🔐 CheckMacValue 生成: {check_mac[:10]}...")
    return check_mac

def save_order(order_id, order_data):
    """儲存訂單到檔案"""
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
# Email 發送
# ==========================================

def send_order_email(order_data, stl_files=None):
    """
    發送訂單通知 Email 到內部信箱
    """
    try:
        logger.info(f"📧 準備發送訂單 Email: {order_data['orderId']}")
        
        # 建立 Email
        msg = MIMEMultipart()
        msg['From'] = f"{EMAIL_CONFIG['sender_name']} <{EMAIL_CONFIG['sender_email']}>"
        msg['To'] = EMAIL_CONFIG['internal_email']
        msg['Subject'] = f"新訂單 - {order_data['orderId']}"
        
        # Email HTML 內容
        html_body = generate_order_email_html(order_data)
        msg.attach(MIMEText(html_body, 'html', 'utf-8'))
        
        # 附加 STL 檔案
        if stl_files:
            for stl_path in stl_files:
                if os.path.exists(stl_path):
                    attach_file(msg, stl_path)
        
        # 發送
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
            
            <details style="margin-top: 10px;">
                <summary style="cursor: pointer; color: #666;">技術參數（點擊展開）</summary>
                <pre style="background: #f5f5f5; padding: 10px; overflow-x: auto; font-size: 12px;">
Letter1 BBox: W={item.get('letter1BBox', {}).get('width', 0):.3f}, H={item.get('letter1BBox', {}).get('height', 0):.3f}, D={item.get('letter1BBox', {}).get('depth', 0):.3f}
Letter2 BBox: W={item.get('letter2BBox', {}).get('width', 0):.3f}, H={item.get('letter2BBox', {}).get('height', 0):.3f}, D={item.get('letter2BBox', {}).get('depth', 0):.3f}
Bail Position: X={item.get('bailAbsoluteX', 0):.3f}, Y={item.get('bailAbsoluteY', 0):.3f}, Z={item.get('bailAbsoluteZ', 0):.3f}
Bail Rotation: {item.get('bailRotation', 0):.1f}°
                </pre>
            </details>
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
            .content {{ padding: 20px; }}
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
            
            <div class="content">
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

# ==========================================
# STL 生成（調用現有的 /generate 端點）
# ==========================================

def generate_stl_for_item(item):
    """
    為單個商品生成 STL
    這會調用現有的 /generate 端點
    """
    # 這個函數假設你的 Flask app 已經有 /generate 端點
    # 我們這裡只是記錄檔案路徑，實際生成由前端觸發或另外實作
    
    filename = f"DUET_{item['letter1']}{item['letter2']}_{item['size']}mm_{item['id']}.stl"
    filepath = os.path.join(STL_DIR, filename)
    
    # TODO: 實際調用 STL 生成邏輯
    # 暫時返回預期路徑
    
    logger.info(f"📦 STL 生成: {filename}")
    return filepath

# ==========================================
# API 端點
# ==========================================

@app.route('/api/checkout', methods=['POST'])
def checkout():
    """
    初始化綠界支付
    """
    try:
        data = request.json
        logger.info(f"💳 收到結帳請求: {data.get('orderId')}")
        
        order_id = data['orderId']
        total = data['total']
        items = data['items']
        user_info = data['userInfo']
        return_url = data.get('returnUrl', request.host_url + 'payment-success')
        
        # 儲存訂單
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
        
        # 建立綠界支付參數
        payment_params = {
            'MerchantID': ECPAY_CONFIG['MerchantID'],
            'MerchantTradeNo': order_id,
            'MerchantTradeDate': datetime.now().strftime('%Y/%m/%d %H:%M:%S'),
            'PaymentType': 'aio',
            'TotalAmount': str(total),
            'TradeDesc': 'DUET客製墜飾',
            'ItemName': f"客製墜飾 x {len(items)}",
            'ReturnURL': 'ReturnURL': request.host_url.rstrip('/') + '/api/payment/callback',
            'ClientBackURL': return_url,
            'ChoosePayment': 'Credit',
            'EncryptType': '1'
        }
        
        # 產生 CheckMacValue
        check_mac_value = generate_check_mac_value(
            payment_params, 
            ECPAY_CONFIG['HashKey'], 
            ECPAY_CONFIG['HashIV']
        )
        payment_params['CheckMacValue'] = check_mac_value
        
        # 建立 HTML 表單
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
    """
    綠界支付回調
    ⚠️ 安全關鍵：驗證支付真實性
    """
    try:
        # 接收綠界回傳資料
        data = request.form.to_dict()
        
        logger.info(f"📥 收到綠界回調: {data.get('MerchantTradeNo')}")
        logger.debug(f"回調資料: {json.dumps(data, ensure_ascii=False)}")
        
        # ⚠️ 安全驗證：CheckMacValue
        received_check_mac = data.pop('CheckMacValue', '')
        calculated_check_mac = generate_check_mac_value(
            data, 
            ECPAY_CONFIG['HashKey'], 
            ECPAY_CONFIG['HashIV']
        )
        
        if received_check_mac != calculated_check_mac:
            logger.error(f"❌ CheckMacValue 驗證失敗！")
            logger.error(f"   收到: {received_check_mac}")
            logger.error(f"   計算: {calculated_check_mac}")
            return '0|CheckMacValue Error'
        
        logger.info("✅ CheckMacValue 驗證通過")
        
        # 檢查付款狀態
        if data.get('RtnCode') == '1':  # 付款成功
            order_id = data['MerchantTradeNo']
            
            logger.info(f"✅ 訂單 {order_id} 付款成功")
            
            # 處理訂單
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
    付款成功後處理訂單
    1. 生成 STL
    2. 發送 Email
    3. 更新訂單狀態
    """
    try:
        logger.info(f"🔄 開始處理訂單: {order_id}")
        
        # 讀取訂單
        order = load_order(order_id)
        if not order:
            logger.error(f"❌ 訂單不存在: {order_id}")
            return False
        
        # 更新支付資訊
        update_order_status(order_id, 'paid', payment_data)
        
        # 生成 STL（這裡可以調用現有的 STL 生成邏輯）
        stl_files = []
        # TODO: 實際 STL 生成
        # for item in order['items']:
        #     stl_path = generate_stl_for_item(item)
        #     stl_files.append(stl_path)
        
        # 發送 Email
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
    """
    測試模式：模擬訂單處理（不經過金流）
    """
    try:
        data = request.json
        logger.info(f"🧪 測試模式訂單: {data.get('orderId')}")
        
        # 儲存訂單
        save_order(data['orderId'], data)
        
        # 發送 Email
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
            .success-icon {
                font-size: 60px;
                color: #4CAF50;
                margin-bottom: 20px;
            }
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

@app.route('/health')
def health():
    """健康檢查"""
    return jsonify({
        'status': 'ok',
        'timestamp': datetime.now().isoformat()
    })

# ==========================================
# 啟動應用
# ==========================================

if __name__ == '__main__':
    print("🚀 DUET Backend 啟動中...")
    print(f"📧 Email: {EMAIL_CONFIG['sender_email']} → {EMAIL_CONFIG['internal_email']}")
    print(f"💳 綠界: {ECPAY_CONFIG['MerchantID']}")
    print(f"📂 訂單目錄: {ORDERS_DIR}")
    print("")
    app.run(debug=True, host='0.0.0.0', port=5001)
