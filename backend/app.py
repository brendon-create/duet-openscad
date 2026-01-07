"""
DUET Backend - 修正金額讀取邏輯
1. 修正 checkout 路由中的 int() 轉換錯誤 (NoneType 檢查)
2. 保留原始 Google Sheets 第一個分頁讀取邏輯
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

# Google Sheets 整合
try:
    from google.oauth2 import service_account
    from googleapiclient.discovery import build
    GOOGLE_SHEETS_ENABLED = True
except ImportError:
    GOOGLE_SHEETS_ENABLED = False
    logger.warning("⚠️ Google Sheets 模組未安裝，將跳過 Sheets 整合")

TEMP_DIR = tempfile.gettempdir()
os.makedirs(TEMP_DIR, exist_ok=True)

# ==========================================
# 配置
# ==========================================

# 綠界配置 (依據上傳原始檔之測試參數)
ECPAY_CONFIG = {
    'MerchantID': '3002607',
    'HashKey': 'pwFHCqoQZGmho4w6',
    'HashIV': 'v77hoKGq4kWxNNUE',
    'ReturnURL': 'https://duet-backend-wlw8.onrender.com/api/payment-callback',
    'ClientBackURL': 'https://brendon-create.github.io/duet-openscad/success.html',
}

# Google Sheets ID
SPREADSHEET_ID = os.environ.get('SPREADSHEET_ID', '1yWreYwIInPInCqYV486N6-C19XoI_q3mDsh3w2G4-g8')
CREDENTIALS_PATH = 'credentials.json'

def get_sheets_service():
    if not GOOGLE_SHEETS_ENABLED or not os.path.exists(CREDENTIALS_PATH):
        return None
    try:
        creds = service_account.Credentials.from_service_account_file(
            CREDENTIALS_PATH, 
            scopes=['https://www.googleapis.com/auth/spreadsheets.readonly']
        )
        return build('sheets', 'v4', credentials=creds)
    except Exception as e:
        logger.error(f"❌ Sheets Service Error: {e}")
        return None

# ==========================================
# 核心加密函式
# ==========================================

def create_check_mac_value(params, hash_key, hash_iv):
    filtered_params = {k: v for k, v in params.items() if k != 'CheckMacValue'}
    sorted_keys = sorted(filtered_params.keys())
    raw_parts = [f"{k}={filtered_params[k]}" for k in sorted_keys]
    raw_string = f"HashKey={hash_key}&{'&'.join(raw_parts)}&HashIV={hash_iv}"
    
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

@app.route('/api/checkout', methods=['POST'])
def checkout():
    try:
        data = request.get_json()
        if not data:
            return jsonify({'success': False, 'error': 'No data provided'}), 400

        # 修正：處理金額可能為 None 或字串的情況
        raw_amount = data.get('amount')
        if raw_amount is None:
            # 如果前端沒傳，嘗試預設值或報錯
            logger.warning("⚠️ Received amount is None, checking total_price fallback")
            raw_amount = data.get('total_price', 5000)
            
        try:
            # 兼容 "5000" (str) 或 5000.0 (float)
            amount = int(float(raw_amount))
        except (ValueError, TypeError):
            amount = 5000

        order_id = data.get('orderId', f"DUET{int(time.time())}")

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

        params['CheckMacValue'] = create_check_mac_value(
            params, ECPAY_CONFIG['HashKey'], ECPAY_CONFIG['HashIV']
        )

        return jsonify({
            'success': True,
            'paymentUrl': 'https://payment-stage.ecpay.com.tw/Cashier/AioCheckOut/V5',
            'params': params
        })
    except Exception as e:
        logger.error(f"❌ Checkout Error: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/validate-promo', methods=['POST'])
def validate_promo():
    """ 從 Google Sheets 驗證優惠碼 (保持原始邏輯) """
    try:
        data = request.get_json()
        input_code = data.get('code', '').strip().upper()
        
        service = get_sheets_service()
        if not service:
            return jsonify({'success': False, 'message': 'Promo service unavailable'}), 500
            
        # 保持原始：不指定 Sheet Name，僅讀取第一個分頁
        result = service.spreadsheets().values().get(
            spreadsheetId=SPREADSHEET_ID,
            range='A:B' # 讀取 A 和 B 欄
        ).execute()
        
        rows = result.get('values', [])
        for row in rows:
            if len(row) >= 2:
                db_code = str(row[0]).strip().upper()
                if db_code == input_code:
                    try:
                        discount = float(row[1])
                        return jsonify({'success': True, 'discount': discount})
                    except:
                        continue
        
        return jsonify({'success': False, 'message': '無效的優惠碼'}), 400
    except Exception as e:
        logger.error(f"❌ Promo error: {e}")
        return jsonify({'success': False, 'message': '伺服器錯誤'}), 500

@app.route('/health')
def health():
    return jsonify({'status': 'ok', 'time': datetime.now().isoformat()})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)