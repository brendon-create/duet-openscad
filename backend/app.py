"""
此文件僅針對 CheckMacValue 生成邏輯進行精確修正。
請將此部分的函式覆蓋您原本 app.py 中的對應部分。
"""

import hashlib
import urllib.parse

def create_check_mac_value(params, hash_key, hash_iv):
    """
    嚴格遵循綠界科技 CheckMacValue 生成規範：
    1. 參數名稱依 A-Z 排序
    2. 組合字串，前後加上 HashKey 與 HashIV
    3. URL 編碼並轉小寫
    4. 執行綠界規定的符號替換 (重點)
    5. SHA256 加密後轉大寫
    """
    # 1. 排除 CheckMacValue 並進行排序
    filtered_params = {k: v for k, v in params.items() if k != 'CheckMacValue'}
    sorted_keys = sorted(filtered_params.keys())
    
    # 2. 組合字串
    raw_parts = [f"{k}={filtered_params[k]}" for k in sorted_keys]
    raw_string = f"HashKey={hash_key}&{'&'.join(raw_parts)}&HashIV={hash_iv}"
    
    # 3. URL Encode (注意：綠界要求這步之後要轉小寫)
    # quote_plus 會將空格編碼為 '+'，符合綠界規範
    encoded_string = urllib.parse.quote_plus(raw_string).lower()
    
    # 4. 特殊字元替換 (綠界規範核心)
    # 根據官方文件，這 8 個符號在編碼後必須替換回來
    replacements = {
        '%2d': '-', 
        '%5f': '_', 
        '%2e': '.', 
        '%21': '!', 
        '%2a': '*', 
        '%28': '(', 
        '%29': ')', 
        '%20': '+'
    }
    for old, new in replacements.items():
        encoded_string = encoded_string.replace(old, new)
        
    # 5. SHA256 加密
    hash_result = hashlib.sha256(encoded_string.encode('utf-8')).hexdigest().upper()
    
    return hash_result

# ==========================================
# 修正後的 Checkout 呼叫段落
# ==========================================

@app.route('/api/checkout', methods=['POST'])
def checkout():
    try:
        data = request.get_json()
        order_id = data.get('orderId')
        amount = int(data.get('amount'))
        
        # 綠界基礎參數
        params = {
            'MerchantID': ECPAY_CONFIG['MerchantID'],
            'MerchantTradeNo': str(order_id),
            'MerchantTradeDate': datetime.now().strftime('%Y/%m/%d %H:%M:%S'),
            'PaymentType': 'aio',
            'TotalAmount': amount,
            'TradeDesc': 'DUET Custom STL Order', # 盡量不要有特殊符號或中文
            'ItemName': 'Custom STL Product',     # 盡量使用簡單字串
            'ReturnURL': ECPAY_CONFIG['ReturnURL'],
            'ChoosePayment': 'ALL',
            'EncryptType': '1',
            'ClientBackURL': ECPAY_CONFIG['ClientBackURL'],
        }

        # 呼叫上面修正後的加密函式
        params['CheckMacValue'] = create_check_mac_value(
            params, 
            ECPAY_CONFIG['HashKey'], 
            ECPAY_CONFIG['HashIV']
        )

        return jsonify({
            'success': True,
            'paymentUrl': 'https://payment-stage.ecpay.com.tw/Cashier/AioCheckOut/V5',
            'params': params
        })
        
    except Exception as e:
        logger.error(f"❌ 結帳出錯: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500

# ==========================================
# 修正後的優惠碼驗證邏輯 (確保不顯示 undefined)
# ==========================================

@app.route('/api/validate-promo', methods=['POST'])
def validate_promo():
    try:
        data = request.get_json()
        if not data:
            return jsonify({'success': False, 'message': '無效的請求'}), 400
            
        code = data.get('code', '').strip().upper()
        
        # 假設 PROMO_CODES = {"VIP10": 0.9}
        if code in PROMO_CODES:
            return jsonify({
                'success': True, 
                'discount': PROMO_CODES[code],
                'message': '優惠碼套用成功！' # 確保有 message 欄位
            })
        else:
            return jsonify({
                'success': False, 
                'message': '查無此優惠碼' # 即使錯誤也要回傳 message
            }), 400
    except Exception as e:
        return jsonify({'success': False, 'message': f'系統錯誤: {str(e)}'}), 500