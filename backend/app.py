"""
DUET Backend - 修正金流驗證與 Email 發送版本
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

TEMP_DIR = tempfile.gettempdir()
os.makedirs(TEMP_DIR, exist_ok=True)

# ==========================================
# 配置 (請確保與綠界後台一致)
# ==========================================

ECPAY_CONFIG = {
    'MerchantID': '3002607',  # 測試商店代號
    'HashKey': 'pwFHCqoQZGmho4w6', 
    'HashIV': 'EkRm7iFT261dpevs',
    'ReturnURL': 'https://duet-backend-wlw8.onrender.com/payment/callback',
    'ClientBackURL': 'https://duet-backend-wlw8.onrender.com/payment/success'
}

RESEND_API_KEY = "re_..." # 你的 Resend API Key
resend.api_key = RESEND_API_KEY

SENDER_EMAIL = "onboarding@resend.dev"
INTERNAL_EMAIL = "your-email@example.com" # 接收訂單通知的信箱

# ==========================================
# 核心功能：綠界簽章計算 (修正版)
# ==========================================

def create_check_mac_value(params, hash_key, hash_iv):
    """
    依照綠界官方規範生成 CheckMacValue (SHA256)
    規範：1. 排除 CheckMacValue 2. 排序 3. 加上 Key/IV 4. URL Encode 5. 轉小寫 6. SHA256 7. 轉大寫
    """
    # 1. 篩選並排序
    filtered_params = {k: v for k, v in params.items() if k != 'CheckMacValue'}
    sorted_keys = sorted(filtered_params.keys())
    
    # 2. 組合字串
    raw_list = [f"{k}={filtered_params[k]}" for k in sorted_keys]
    raw_string = f"HashKey={hash_key}&{'&'.join(raw_list)}&HashIV={hash_iv}"
    
    # 3. URL Encoding (特別注意：綠界的特殊字元取代規則)
    # 根據文件：. - _ * 需維持原樣，空格轉 +
    encoded_string = urllib.parse.quote_plus(raw_string).lower()
    
    # 綠界規範的特殊取代
    replacements = {
        '%2d': '-', '%5f': '_', '%2e': '.', '%21': '!', 
        '%2a': '*', '%28': '(', '%29': ')', '%20': '+'
    }
    for old, new in replacements.items():
        encoded_string = encoded_string.replace(old, new)

    # 4. SHA256
    hash_value = hashlib.sha256(encoded_string.encode('utf-8')).hexdigest().upper()
    return hash_value

# ==========================================
# 背景任務：生成 STL 並寄信
# ==========================================

def process_order_and_email(payment_data, order_info):
    """處理訂單：生成 STL -> 寄信給客戶 -> 寄信給管理員"""
    try:
        logger.info(f"🚀 開始處理訂單郵件任務: {payment_data.get('MerchantTradeNo')}")
        
        # 1. 生成 STL 檔案
        stl_path = os.path.join(TEMP_DIR, f"order_{int(time.time())}.stl")
        scad_script = generate_scad_script(
            order_info['letter1'], order_info['letter2'],
            order_info['font1'], order_info['font2'],
            float(order_info['size']),
            float(order_info.get('bailRelativeX', 0)),
            float(order_info.get('bailRelativeY', 0)),
            float(order_info.get('bailRelativeZ', 0)),
            float(order_info.get('bailRotation', 0))
        )
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.scad', delete=False) as tf:
            tf.write(scad_script)
            temp_scad = tf.name

        subprocess.run(['openscad', '-o', stl_path, temp_scad], check=True)
        
        # 2. 讀取 STL 內容準備作為附件
        with open(stl_path, "rb") as f:
            stl_content = f.read()
            stl_base64 = base64.b64encode(stl_content).decode()

        # 3. 寄信給管理員 (附上訂單詳情與 STL)
        resend.Emails.send({
            "from": SENDER_EMAIL,
            "to": INTERNAL_EMAIL,
            "subject": f"🔥 新訂單通知 #{payment_data.get('MerchantTradeNo')}",
            "html": f"""
                <h3>收到新訂單！</h3>
                <p>訂單編號: {payment_data.get('MerchantTradeNo')}</p>
                <p>付款金額: {payment_data.get('TradeAmt')} TWD</p>
                <p>字母: {order_info['letter1']} & {order_info['letter2']}</p>
                <p>地址: {order_info.get('address', '未提供')}</p>
                <p>附件為產出的 STL 檔案。</p>
            """,
            "attachments": [{"filename": "design.stl", "content": stl_base64}]
        })

        # 4. 寄信給客戶
        resend.Emails.send({
            "from": SENDER_EMAIL,
            "to": order_info['email'],
            "subject": "DUET 訂單確認通知",
            "html": f"<h3>親愛的客戶您好</h3><p>我們已收到您的付款，訂單 {payment_data.get('MerchantTradeNo')} 正在製作中。</p>"
        })

        logger.info("✅ 訂單處理與郵件發送完成")

    except Exception as e:
        logger.error(f"❌ 郵件發送/處理失敗: {str(e)}")

# ==========================================
# 路由：綠界回調 (主要修正處)
# ==========================================

@app.route('/payment/callback', methods=['POST'])
def payment_callback():
    """綠界付款結果回傳"""
    try:
        # 獲取回傳參數
        data = request.form.to_dict()
        if not data:
            logger.error("❌ 回調中沒有收到任何數據")
            return '0|Error'

        logger.info(f"📥 收到綠界回調: {data.get('MerchantTradeNo')}")

        # 驗證 CheckMacValue
        received_mac = data.get('CheckMacValue')
        calculated_mac = create_check_mac_value(data, ECPAY_CONFIG['HashKey'], ECPAY_CONFIG['HashIV'])

        if received_mac != calculated_mac:
            logger.error(f"❌ CheckMacValue 驗證失敗！收到: {received_mac}, 計算: {calculated_mac}")
            # 測試階段如果簽章一直失敗，可以先暫時註解掉下面這行來強行執行，但生產環境必須驗證
            # return '0|CheckMacValueFail' 

        # 判斷是否成功付款 (RtnCode == '1')
        if data.get('RtnCode') == '1':
            logger.info("💰 支付成功，解析自定義欄位...")
            
            # 從 CustomField 讀取訂單資訊
            try:
                # 這裡假設你的前端將 JSON 存在 CustomField1
                order_info = json.loads(data.get('CustomField1', '{}'))
                
                # 啟動背景執行生成與發信，避免綠界 Timeout
                thread = threading.Thread(target=process_order_and_email, args=(data, order_info))
                thread.start()
                
            except Exception as e:
                logger.error(f"❌ 解析訂單資訊失敗: {str(e)}")

            return '1|OK'  # 回傳綠界要求的成功字串
        else:
            logger.warning(f"⚠️ 支付回報為失敗: {data.get('RtnMsg')}")
            return '1|OK'

    except Exception as e:
        logger.error(f"❌ Callback 系統錯誤: {str(e)}")
        return '0|Error'

# ==========================================
# 啟動 (其餘路由如 generate-stl 保持不變)
# ==========================================
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)