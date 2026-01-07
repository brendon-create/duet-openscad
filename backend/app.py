"""
DUET Backend - 修正路由路徑與 API 銜接版本
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
# 允許所有來源進行跨域請求，這對前端與後端分開部署至關重要
CORS(app, resources={r"/*": {"origins": "*"}})

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

ECPAY_CONFIG = {
    'MerchantID': '3002607', 
    'HashKey': 'pwFHCqoQZGmho4w6', 
    'HashIV': 'EkRm7iFT261dpevs',
    'ReturnURL': 'https://duet-backend-wlw8.onrender.com/payment/callback',
    'ClientBackURL': 'https://duet-backend-wlw8.onrender.com/payment/success'
}

# 請替換為您的有效 API KEY
RESEND_API_KEY = "re_..." 
resend.api_key = RESEND_API_KEY

SENDER_EMAIL = "onboarding@resend.dev"
INTERNAL_EMAIL = "your-email@example.com"

# ==========================================
# 工具函式
# ==========================================

def create_check_mac_value(params, hash_key, hash_iv):
    filtered_params = {k: v for k, v in params.items() if k != 'CheckMacValue'}
    sorted_keys = sorted(filtered_params.keys())
    raw_list = [f"{k}={filtered_params[k]}" for k in sorted_keys]
    raw_string = f"HashKey={hash_key}&{'&'.join(raw_list)}&HashIV={hash_iv}"
    
    encoded_string = urllib.parse.quote_plus(raw_string).lower()
    replacements = {
        '%2d': '-', '%5f': '_', '%2e': '.', '%21': '!', 
        '%2a': '*', '%28': '(', '%29': ')', '%20': '+'
    }
    for old, new in replacements.items():
        encoded_string = encoded_string.replace(old, new)

    return hashlib.sha256(encoded_string.encode('utf-8')).hexdigest().upper()

# ==========================================
# API 路由
# ==========================================

@app.route('/health')
@app.route('/api/health') # 同時支援兩種路徑
def health():
    """健康檢查，解決前端 Log 中的 404"""
    return jsonify({'status': 'ok', 'message': 'DUET Backend is running'})

@app.route('/list-fonts')
@app.route('/api/list-fonts')
def list_fonts():
    """回傳系統可用字體，解決前端 Log 中的 404"""
    # 這裡回傳一個基礎清單，或你可以掃描系統字體
    return jsonify(['Alice', 'Roboto', 'Open Sans', 'Lato'])

@app.route('/api/checkout', methods=['POST', 'OPTIONS'])
def checkout():
    """前端點擊結帳時呼叫的 API"""
    if request.method == 'OPTIONS':
        return '', 204
        
    try:
        data = request.json
        order_id = data.get('orderId', f"DUET{int(time.time() * 1000)}")
        amount = data.get('amount', 5000)
        
        # 準備綠界參數
        params = {
            'MerchantID': ECPAY_CONFIG['MerchantID'],
            'MerchantTradeNo': order_id,
            'MerchantTradeDate': datetime.now().strftime('%Y/%m/%d %H:%M:%S'),
            'PaymentType': 'aio',
            'TotalAmount': amount,
            'TradeDesc': urllib.parse.quote('DUET Custom Jewelry'),
            'ItemName': 'Custom STL Design',
            'ReturnURL': ECPAY_CONFIG['ReturnURL'],
            'ChoosePayment': 'ALL',
            'EncryptType': '1',
            'ClientBackURL': ECPAY_CONFIG['ClientBackURL'],
            'CustomField1': json.dumps(data.get('orderInfo', {})) # 儲存訂單細節
        }
        
        params['CheckMacValue'] = create_check_mac_value(params, ECPAY_CONFIG['HashKey'], ECPAY_CONFIG['HashIV'])
        
        return jsonify({
            'success': True,
            'paymentUrl': 'https://payment-stage.ecpay.com.tw/Cashier/AioCheckOut/V5',
            'params': params
        })
    except Exception as e:
        logger.error(f"結帳出錯: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/payment/callback', methods=['POST'])
def payment_callback():
    """綠界付款成功回調"""
    data = request.form.to_dict()
    # 驗證邏輯... (略，保持上方修正版內容)
    return '1|OK'

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)