"""
DUET Backend - 基於原版完整修正
修正重點：
1. 補齊 /api 前綴路由（與前端對齊）
2. 修正 CheckMacValue 演算法與綠界規範一致
3. 增加 /api/validate-promo 路由
4. 修正 CORS 預檢（OPTIONS）
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
# 修正 CORS：明確允許 OPTIONS 請求與 Content-Type Header
CORS(app, resources={r"/*": {"origins": "*"}}, supports_credentials=True)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

TEMP_DIR = tempfile.gettempdir()
os.makedirs(TEMP_DIR, exist_ok=True)

# ==========================================
# 配置
# ==========================================

# 綠界配置 (建議檢查是否為測試環境)
ECPAY_CONFIG = {
    'MerchantID': '3002607', 
    'HashKey': 'pwFHCqoQZGmho4w6', 
    'HashIV': 'EkRm7iFT261dpevs',
    'ReturnURL': 'https://duet-backend-wlw8.onrender.com/api/payment/callback',
    'ClientBackURL': 'https://duet-backend-wlw8.onrender.com/payment/success'
}

# 優惠碼配置
PROMO_CODES = {
    "VIP10": 0.9,
    "OPENING": 0.8
}

RESEND_API_KEY = "re_..." # 請填入您的 KEY
resend.api_key = RESEND_API_KEY
SENDER_EMAIL = "onboarding@resend.dev"
INTERNAL_EMAIL = "your-email@example.com"

# ==========================================
# 工具函式
# ==========================================

def create_check_mac_value(params, hash_key, hash_iv):
    """綠界官方標準 CheckMacValue 演算法"""
    # 1. 排除 CheckMacValue 並依字母順序排序
    filtered_params = {k: v for k, v in params.items() if k != 'CheckMacValue'}
    sorted_keys = sorted(filtered_params.keys())
    
    # 2. 組合字串
    raw_list = [f"{k}={filtered_params[k]}" for k in sorted_keys]
    raw_string = f"HashKey={hash_key}&{'&'.join(raw_list)}&HashIV={hash_iv}"
    
    # 3. URL Encode
    encoded_string = urllib.parse.quote_plus(raw_string).lower()
    
    # 4. 根據綠界規範替換特定字元 (Symbol replacement)
    replacements = {
        '%2d': '-', '%5f': '_', '%2e': '.', '%21': '!', 
        '%2a': '*', '%28': '(', '%29': ')', '%20': '+'
    }
    for old, new in replacements.items():
        encoded_string = encoded_string.replace(old, new)

    # 5. SHA256 並轉大寫
    return hashlib.sha256(encoded_string.encode('utf-8')).hexdigest().upper()

# ==========================================
# API 路由
# ==========================================

@app.route('/api/health')
@app.route('/health')
def health():
    return jsonify({'status': 'ok', 'message': 'DUET Backend is active'})

@app.route('/api/validate-promo', methods=['POST', 'OPTIONS'])
def validate_promo():
    """處理優惠碼驗證"""
    if request.method == 'OPTIONS':
        return '', 204
    try:
        data = request.json
        code = data.get('code', '').upper()
        if code in PROMO_CODES:
            return jsonify({
                'success': True, 
                'discount': PROMO_CODES[code],
                'message': '優惠碼已套用'
            })
        return jsonify({'success': False, 'message': '無效的優惠碼'}), 400
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/checkout', methods=['POST', 'OPTIONS'])
def checkout():
    """發起結帳"""
    if request.method == 'OPTIONS':
        return '', 204
        
    try:
        data = request.json
        # 從前端獲取資訊
        order_id = data.get('orderId', f"DUET{int(time.time() * 1000)}")
        amount = int(data.get('amount', 5000))
        user_info = data.get('userInfo', {})
        
        # 準備綠界標準參數
        params = {
            'MerchantID': ECPAY_CONFIG['MerchantID'],
            'MerchantTradeNo': str(order_id),
            'MerchantTradeDate': datetime.now().strftime('%Y/%m/%d %H:%M:%S'),
            'PaymentType': 'aio',
            'TotalAmount': amount,
            'TradeDesc': 'DUET Custom Jewelry Order',
            'ItemName': 'Custom STL Design',
            'ReturnURL': ECPAY_CONFIG['ReturnURL'],
            'ChoosePayment': 'ALL',
            'EncryptType': '1',
            'ClientBackURL': ECPAY_CONFIG['ClientBackURL'],
            # 利用自定義欄位存儲資訊，避免遺失
            'CustomField1': user_info.get('email', ''),
            'CustomField2': base64.b64encode(json.dumps(data.get('orderInfo', {})).encode()).decode()[:200]
        }
        
        # 生成簽章
        params['CheckMacValue'] = create_check_mac_value(params, ECPAY_CONFIG['HashKey'], ECPAY_CONFIG['HashIV'])
        
        return jsonify({
            'success': True,
            'paymentUrl': 'https://payment-stage.ecpay.com.tw/Cashier/AioCheckOut/V5',
            'params': params
        })
    except Exception as e:
        logger.error(f"結帳出錯: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/payment/callback', methods=['POST'])
def payment_callback():
    """接收綠界付款結果通知 (Server-to-Server)"""
    data = request.form.to_dict()
    # 這裡放您原本的隊列與寄信邏輯...
    # (省略部分與原本 app.py 一致)
    logger.info(f"收到支付通知: {data.get('MerchantTradeNo')}")
    return '1|OK'

# 其餘 STL 生成路由 (/api/generate 等) 請維持您原本的程式碼...
# ...