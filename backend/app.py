"""
DUET Backend - 修正綠界 CheckMacValue 加密邏輯版本
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
# 1. Flask 應用初始化 (必須在路由之前)
# ==========================================
app = Flask(__name__)
CORS(app)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# 配置目錄
TEMP_DIR = tempfile.gettempdir()
os.makedirs(TEMP_DIR, exist_ok=True)

# ==========================================
# 2. 配置資訊 (請填入您的正確金鑰)
# ==========================================
ECPAY_CONFIG = {
    'MerchantID': '3317971',
    'HashKey': 'MN7lld33ls2A7ACQ',
    'HashIV': 'JsQNlwsz3mUv016X',
    'ReturnURL': 'https://duet-backend.onrender.com/api/payment-callback',
    'ClientBackURL': 'https://brendon-create.github.io/duet-openscad/success.html',
    'OrderResultURL': 'https://brendon-create.github.io/duet-openscad/success.html'
}

# ==========================================
# 3. 核心加密函式 (嚴格遵循綠界規範)
# ==========================================
def create_check_mac_value(params, hash_key, hash_iv):
    """
    綠界 CheckMacValue 生成步驟：
    1. 參數名稱依 A-Z 排序，排除 CheckMacValue
    2. 組合字串：HashKey=xxx&Key1=Value1&...&HashIV=xxx
    3. URL Encode 並轉為小寫
    4. 執行綠界特定的符號替換 (Dot Net 風格)
    5. SHA256 加密並轉大寫
    """
    # 1. 排序與排除
    filtered_params = {k: v for k, v in params.items() if k != 'CheckMacValue'}
    sorted_keys = sorted(filtered_params.keys())
    
    # 2. 組合原始字串
    raw_parts = [f"{k}={filtered_params[k]}" for k in sorted_keys]
    raw_string = f"HashKey={hash_key}&{'&'.join(raw_parts)}&HashIV={hash_iv}"
    
    # 3. URL Encode 且必須小寫化
    # quote_plus 會把空格編碼為 + 號，這符合綠界規範
    encoded_string = urllib.parse.quote_plus(raw_string).lower()
    
    # 4. 關鍵符號替換 (根據綠界 API 規範文件)
    # 這些符號在編碼後必須轉回原始符號，否則 CheckMacValue 會出錯
    replacements = {
        '%2d': '-', 
        '%5f': '_', 
        '%2e': '.', 
        '%21': '!', 
        '%2a': '*', 
        '%28': '(', 
        '%29': ')',
        '%20': '+'  # 確保空格編碼正確
    }
    for old, new in replacements.items():
        encoded_string = encoded_string.replace(old, new)
        
    # 5. SHA256 加密轉大寫
    hash_result = hashlib.sha256(encoded_string.encode('utf-8')).hexdigest().upper()
    return hash_result

# ==========================================
# 4. API 路由
# ==========================================

@app.route('/api/checkout', methods=['POST'])
def checkout():
    try:
        data = request.get_json()
        order_id = data.get('orderId')
        amount = int(data.get('amount'))
        
        # 綠界基礎參數
        # 注意：ItemName 和 TradeDesc 建議不要有特殊符號或中文以減少編碼問題
        params = {
            'MerchantID': ECPAY_CONFIG['MerchantID'],
            'MerchantTradeNo': str(order_id),
            'MerchantTradeDate': datetime.now().strftime('%Y/%m/%d %H:%M:%S'),
            'PaymentType': 'aio',
            'TotalAmount': amount,
            'TradeDesc': 'DUET_ORDER',
            'ItemName': 'DUET_PRODUCT',
            'ReturnURL': ECPAY_CONFIG['ReturnURL'],
            'ChoosePayment': 'ALL',
            'EncryptType': '1',
            'ClientBackURL': ECPAY_CONFIG['ClientBackURL'],
        }

        # 生成檢查碼
        params['CheckMacValue'] = create_check_mac_value(
            params, 
            ECPAY_CONFIG['HashKey'], 
            ECPAY_CONFIG['HashIV']
        )

        logger.info(f"✅ 生成 CheckMacValue: {params['CheckMacValue']} 對於訂單 {order_id}")

        return jsonify({
            'success': True,
            'paymentUrl': 'https://payment-stage.ecpay.com.tw/Cashier/AioCheckOut/V5',
            'params': params
        })
        
    except Exception as e:
        logger.error(f"❌ 結帳錯誤: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/validate-promo', methods=['POST'])
def validate_promo():
    # 修正原本可能導致前端 undefined 的訊息結構
    PROMO_CODES = {"VIP10": 0.9}
    data = request.get_json()
    code = data.get('code', '').strip().upper()
    
    if code in PROMO_CODES:
        return jsonify({
            'success': True, 
            'discount': PROMO_CODES[code],
            'message': '優惠碼已套用'
        })
    return jsonify({
        'success': False, 
        'message': '無效的優惠碼'
    }), 400

@app.route('/health')
def health():
    return jsonify({'status': 'ok', 'time': datetime.now().isoformat()})

# ==========================================
# 5. 啟動 (由 Gunicorn 呼叫)
# ==========================================
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)