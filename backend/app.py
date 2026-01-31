#!/usr/bin/env python3
# -*- coding: utf-8 -*-

# ========================================
# 修正工作目錄（必須在所有 import 之前）
# ========================================
import os
import sys

# 獲取腳本所在目錄
script_dir = os.path.dirname(os.path.abspath(__file__))

# 切換到腳本所在目錄
os.chdir(script_dir)

# 將目錄加入 Python path
if script_dir not in sys.path:
    sys.path.insert(0, script_dir)

# Debug 輸出（部署後可以在 Logs 看到）
print("=" * 60)
print("🔍 腳本位置:", __file__)
print("🔍 工作目錄:", os.getcwd())
print("🔍 目錄內容:", sorted(os.listdir(".")))

for folder in ["models", "prompts"]:
    if os.path.exists(folder):
        print(f"✅ {folder}/ 存在，內容:", os.listdir(folder))
    else:
        print(f"❌ {folder}/ 不存在")

print("=" * 60)
# ========================================

from flask import Flask, request, jsonify
from flask_cors import CORS

# ... 其他 imports
"""
DUET Backend - 完整版（使用 Resend Email）
包含：STL 生成、綠界金流、Resend Email、隊列系統
"""
# ========== DEBUG 開始 ==========
import os
import sys

print("=" * 60)
print("🔍 當前目錄:", os.getcwd())
print("📂 目錄內容:", os.listdir("."))
print("✅ ai_service.py 存在:", os.path.exists("ai_service.py"))
if os.path.exists("ai_service.py"):
    print("📄 大小:", os.path.getsize("ai_service.py"), "bytes")
print("=" * 60)
# ========== DEBUG 結束 ==========
from flask import Flask, request, jsonify, send_file
from flask_cors import CORS

import subprocess
import tempfile
from scad_generator import generate_scad_script
import logging
import hashlib
import urllib.parse
from datetime import datetime
import json
import sib_api_v3_sdk
from sib_api_v3_sdk.rest import ApiException
import threading
import time
import base64
import gspread
from models.prompt_manager import PromptManager
import traceback  # ← 加入這行

# ai_service.py - DUET AI 諮詢服務

import anthropic
import json
import re
import os

# API Key - 使用環境變量
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")

# Initialize Anthropic client
client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

# System Prompt Manager - 動態載入外部 Prompt
prompt_manager = PromptManager("prompts/system_prompt.md")
SYSTEM_PROMPT = prompt_manager.load_prompt()

# 如果外部 Prompt 載入失敗，使用 fallback（不應該發生）
if not SYSTEM_PROMPT:
    print("❌ 致命錯誤：無法載入 System Prompt")
    # 這裡可以加上緊急 fallback 或停止服務
    raise Exception("System Prompt 載入失敗，請檢查 prompts/system_prompt.md 是否存在")


# ==========================================
# Flask 應用初始化
# ==========================================

app = Flask(__name__)
CORS(app)

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
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

TEMP_DIR = tempfile.gettempdir()
os.makedirs(TEMP_DIR, exist_ok=True)

# ==========================================
# 配置
# ==========================================

# 綠界配置
ECPAY_CONFIG = {
    "MerchantID": "3002607",  # ✅ 綠界官方測試商店代號
    "HashKey": "pwFHCqoQZGmho4w6",  # ✅ 測試 HashKey
    "HashIV": "EkRm7iFT261dpevs",  # ✅ 測試 HashIV
    "PaymentURL": "https://payment-stage.ecpay.com.tw/Cashier/AioCheckOut/V5",  # ✅ 測試站
}

# Resend Email 配置
RESEND_API_KEY = "re_Vy8zWUJ2_KhUfFBXD5qiPEVPPsLAghgGr"
SENDER_EMAIL = "service@mail.brendonchen.com"
SENDER_NAME = "DUET 客製珠寶 (請勿回覆)"
INTERNAL_EMAIL = "brendon@brendonchen.com"

# 設定 Brevo API Key
configuration = sib_api_v3_sdk.Configuration()
configuration.api_key["api-key"] = os.getenv("BREVO_API_KEY")
api_instance = sib_api_v3_sdk.TransactionalEmailsApi(
    sib_api_v3_sdk.ApiClient(configuration)
)

# Google Sheets 配置（訂單記錄）
SHEETS_ID = os.environ.get("SHEETS_ID", "")  # 訂單記錄用的 Sheet ID
GOOGLE_CREDENTIALS_JSON = os.environ.get(
    "GOOGLE_CREDENTIALS_JSON", ""
)  # Service Account JSON

# Google Sheets 配置（優惠碼管理）
GOOGLE_SHEETS_CONFIG = {
    "enabled": os.environ.get("GOOGLE_SHEETS_ENABLED", "false").lower() == "true",
    "sheet_id": os.environ.get("PROMO_SHEET_ID", ""),
    "range_name": "A2:I",  # 不指定 Sheet 名稱，使用第一個 sheet
    "cache_duration": 3600,  # 快取 1 小時
}

# 優惠碼快取
PROMO_CODES_CACHE = {"data": {}, "last_updated": None}

# 目錄配置
ORDERS_DIR = "orders"
STL_DIR = "stl_files"
QUEUE_DIR = "stl_queue"
os.makedirs(ORDERS_DIR, exist_ok=True)
os.makedirs(STL_DIR, exist_ok=True)
os.makedirs(QUEUE_DIR, exist_ok=True)

# ==========================================
# 優惠碼系統（完全使用 Google Sheets）
# ==========================================

# ⚠️ 優惠碼完全由 Google Sheets 管理
# 請在 Google Sheets 中設定優惠碼
# Sheet ID: 1qituunsVbUJmJCeoPKKOK02LjyNqzN2AYOuZ_D920IU
#
# 不再使用硬編碼的預設優惠碼！
# 所有優惠碼都從 Google Sheets 載入

PROMO_CODES = {}  # 不使用預設值，完全依賴 Google Sheets


def load_promo_codes_from_sheets():
    """從 Google Sheets 載入優惠碼"""
    global PROMO_CODES_CACHE

    # 檢查是否啟用 Google Sheets
    if not GOOGLE_SHEETS_CONFIG["enabled"]:
        logger.warning("⚠️ Google Sheets 未啟用，無優惠碼可用")
        logger.warning("⚠️ 請在 Render 設定 GOOGLE_SHEETS_ENABLED=true")
        # 返回快取（如果有）或空字典
        return PROMO_CODES_CACHE["data"] if PROMO_CODES_CACHE["data"] else {}

    # 檢查快取是否有效（1小時內）
    if PROMO_CODES_CACHE["last_updated"]:
        cache_age = (datetime.now() - PROMO_CODES_CACHE["last_updated"]).total_seconds()
        if cache_age < GOOGLE_SHEETS_CONFIG["cache_duration"]:
            logger.info(f"📊 使用快取的優惠碼（{int(cache_age)}秒前更新）")
            return PROMO_CODES_CACHE["data"]

    try:
        logger.info("📊 從 Google Sheets 載入優惠碼...")

        # 載入憑證
        if not GOOGLE_CREDENTIALS_JSON:
            logger.error("❌ Google Sheets 憑證未設定")
            logger.error("❌ 請在 Render 設定 GOOGLE_CREDENTIALS_JSON")
            # 返回快取（如果有）或空字典
            return PROMO_CODES_CACHE["data"] if PROMO_CODES_CACHE["data"] else {}

        if GOOGLE_SHEETS_ENABLED:
            import json
            from google.oauth2 import service_account
            from googleapiclient.discovery import build

            # 解析憑證
            creds_dict = json.loads(GOOGLE_CREDENTIALS_JSON)
            credentials = service_account.Credentials.from_service_account_info(
                creds_dict,
                scopes=["https://www.googleapis.com/auth/spreadsheets.readonly"],
            )

            # 建立 Sheets API 服務
            service = build("sheets", "v4", credentials=credentials)
            sheet = service.spreadsheets()

            # 讀取資料
            result = (
                sheet.values()
                .get(
                    spreadsheetId=GOOGLE_SHEETS_CONFIG["sheet_id"],
                    range=GOOGLE_SHEETS_CONFIG["range_name"],
                )
                .execute()
            )

            values = result.get("values", [])

            if not values:
                logger.warning("⚠️ Google Sheets 沒有資料")
                logger.warning("⚠️ 請在 Sheet 中添加優惠碼資料")
                # 返回快取（如果有）或空字典
                return PROMO_CODES_CACHE["data"] if PROMO_CODES_CACHE["data"] else {}

            # 解析資料
            promo_codes = {}
            for row in values:
                if len(row) < 7:  # 至少需要 7 個欄位
                    continue

                code = row[0].strip().upper()
                if not code:
                    continue

                promo_codes[code] = {
                    "type": row[1].lower() if len(row) > 1 else "percentage",
                    "value": float(row[2]) if len(row) > 2 else 0,
                    "minAmount": float(row[3]) if len(row) > 3 else 0,
                    "validUntil": row[5] if len(row) > 5 else "2099-12-31",
                    "active": row[6].upper() == "TRUE" if len(row) > 6 else True,
                    "description": row[7] if len(row) > 7 else "",
                }

            # 更新快取
            PROMO_CODES_CACHE["data"] = promo_codes
            PROMO_CODES_CACHE["last_updated"] = datetime.now()

            logger.info(f"✅ 已載入 {len(promo_codes)} 個優惠碼")
            return promo_codes

    except Exception as e:
        logger.error(f"❌ 從 Google Sheets 載入優惠碼失敗: {e}")
        logger.info("📊 嘗試使用快取的優惠碼")
        # 返回快取（如果有）或空字典
        if PROMO_CODES_CACHE["data"]:
            logger.info(f"✅ 使用快取的 {len(PROMO_CODES_CACHE['data'])} 個優惠碼")
            return PROMO_CODES_CACHE["data"]
        else:
            logger.error("❌ 無快取可用，無優惠碼可用")
            return {}


def validate_promo_code(promo_code, original_total):
    """
    驗證優惠碼並計算折扣金額

    Returns:
        tuple: (is_valid, discount_amount, promo_info, error_message)
    """
    if not promo_code:
        return False, 0, None, None

    code = promo_code.upper().strip()

    # 動態載入優惠碼（會使用快取）
    promo_codes = load_promo_codes_from_sheets()

    # 檢查優惠碼是否存在
    if code not in promo_codes:
        return False, 0, None, "無效的優惠碼"

    promo = promo_codes[code]

    # 檢查是否啟用
    if not promo.get("active", False):
        return False, 0, None, "此優惠碼已失效"

    # 檢查有效期限
    valid_until = promo.get("validUntil")
    if valid_until:
        try:
            # 支持多種日期格式
            date_formats = ["%Y-%m-%d", "%Y/%m/%d", "%Y/%m/%d", "%Y-%m-%d"]
            expiry_date = None
            for fmt in date_formats:
                try:
                    expiry_date = datetime.strptime(valid_until, fmt)
                    break
                except:
                    continue

            if expiry_date and datetime.now() > expiry_date:
                return False, 0, None, "此優惠碼已過期"
        except:
            pass

    # 檢查最低消費金額
    min_amount = promo.get("minAmount", 0)
    if original_total < min_amount:
        return False, 0, None, f"此優惠碼需滿 NT$ {min_amount:,} 才可使用"

    # 計算折扣
    discount = 0
    if promo["type"] == "percentage":
        discount = int(original_total * promo["value"] / 100)
    elif promo["type"] == "fixed":
        discount = promo["value"]

    # 確保折扣不超過總金額
    discount = min(discount, original_total)

    logger.info(f"✅ 優惠碼驗證成功: {code}, 折扣: NT$ {discount}")

    return True, discount, promo, None


# ==========================================
# 訂單管理（獨立檔案儲存）
# ==========================================


def save_order(order_id, order_data):
    """儲存訂單到獨立檔案"""
    filepath = os.path.join(ORDERS_DIR, f"{order_id}.json")
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(order_data, f, ensure_ascii=False, indent=2)
    logger.info(f"✅ 訂單已儲存: {order_id}")


def load_order(order_id):
    """讀取訂單"""
    filepath = os.path.join(ORDERS_DIR, f"{order_id}.json")
    if not os.path.exists(filepath):
        return None
    with open(filepath, "r", encoding="utf-8") as f:
        return json.load(f)


def update_order_status(order_id, status, payment_data=None):
    """更新訂單狀態"""
    order = load_order(order_id)
    if not order:
        return False
    order["status"] = status
    order["updated_at"] = datetime.now().isoformat()
    if payment_data:
        order["payment_data"] = payment_data
    save_order(order_id, order)
    logger.info(f"📝 訂單狀態: {order_id} → {status}")
    return True


# ==========================================
# Google Sheets 整合
# ==========================================


def save_to_google_sheets(order_data):
    """儲存訂單到 Google Sheets"""
    if not GOOGLE_SHEETS_ENABLED or not SHEETS_ID or not GOOGLE_CREDENTIALS_JSON:
        logger.warning("⚠️ Google Sheets 未啟用，跳過")
        return

    try:
        # 載入憑證
        import tempfile

        creds_file = tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".json")
        creds_file.write(GOOGLE_CREDENTIALS_JSON)
        creds_file.close()

        creds = service_account.Credentials.from_service_account_file(
            creds_file.name, scopes=["https://www.googleapis.com/auth/spreadsheets"]
        )
        service = build("sheets", "v4", credentials=creds)

        # 準備資料行
        items = order_data.get("items", [])
        item1 = json.dumps(items[0], ensure_ascii=False) if len(items) > 0 else ""
        item2 = json.dumps(items[1], ensure_ascii=False) if len(items) > 1 else ""
        item3 = json.dumps(items[2], ensure_ascii=False) if len(items) > 2 else ""

        # 原始金額和結帳金額
        original_total = order_data.get("originalTotal", order_data.get("total", 0))
        final_total = order_data.get("total", 0)
        promo_code = order_data.get("promoCode", "")

        # AI 諮詢資料（轉為 JSON 字串）
        ai_consultation = order_data.get("aiConsultation")
        ai_consultation_str = (
            json.dumps(ai_consultation, ensure_ascii=False) if ai_consultation else ""
        )

        row = [
            order_data.get("orderId", ""),  # A: 訂單編號
            order_data.get("userInfo", {}).get("name", ""),  # B: 客戶姓名
            order_data.get("userInfo", {}).get("email", ""),  # C: Email
            order_data.get("userInfo", {}).get("phone", ""),  # D: 電話
            item1,  # E: 商品1
            item2,  # F: 商品2
            item3,  # G: 商品3
            original_total,  # H: 總金額（原價）
            promo_code,  # I: 優惠碼
            final_total,  # J: 結帳金額
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),  # K: 建立時間
            order_data.get("status", "pending"),  # L: 狀態
            ai_consultation_str,  # M: AI 諮詢資料（新增）
        ]

        # 寫入 Google Sheets（不指定分頁名稱，使用第一個分頁）
        service.spreadsheets().values().append(
            spreadsheetId=SHEETS_ID,
            range="A:M",  # 擴展到 M 欄
            valueInputOption="RAW",
            body={"values": [row]},
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
        "order_id": order_id,
        "added_at": datetime.now().isoformat(),
        "retry_count": 0,
        "status": "pending",
    }

    queue_file = os.path.join(QUEUE_DIR, f"{order_id}.json")
    with open(queue_file, "w", encoding="utf-8") as f:
        json.dump(queue_item, f, ensure_ascii=False, indent=2)

    logger.info(f"✅ 訂單 {order_id} 已加入 STL 隊列")


def get_pending_queue_items():
    """取得待處理的隊列項目"""
    items = []
    try:
        for filename in os.listdir(QUEUE_DIR):
            if filename.endswith(".json"):
                filepath = os.path.join(QUEUE_DIR, filename)
                try:
                    with open(filepath, "r", encoding="utf-8") as f:
                        item = json.load(f)
                        if item.get("status") == "pending":
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
    order_id = item["order_id"]
    retry_count = item.get("retry_count", 0)

    logger.info(f"🔨 處理訂單: {order_id}")

    try:
        success = generate_and_send_stl(order_id)

        if success:
            remove_from_queue(queue_file)
            update_order_status(order_id, "completed")
            logger.info(f"✅ 訂單 {order_id} 處理完成")
        else:
            if retry_count < 3:
                item["retry_count"] = retry_count + 1
                with open(queue_file, "w", encoding="utf-8") as f:
                    json.dump(item, f, ensure_ascii=False, indent=2)
                logger.warning(f"⚠️ 訂單 {order_id} 失敗，將重試 ({retry_count + 1}/3)")
            else:
                item["status"] = "failed"
                with open(queue_file, "w", encoding="utf-8") as f:
                    json.dump(item, f, ensure_ascii=False, indent=2)
                update_order_status(order_id, "stl_failed")
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

    lock_file = "/tmp/duet_worker.lock"

    try:
        # 嘗試取得鎖
        lock_fd = open(lock_file, "w")
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

        # 只傳送 scad_generator 需要的 9 個參數
        params = {
            "letter1": item["letter1"],
            "letter2": item["letter2"],
            "font1": item["font1"],
            "font2": item["font2"],
            "size": item["size"],
            "bailRelativeX": item.get("bailRelativeX", 0),
            "bailRelativeY": item.get("bailRelativeY", 0),
            "bailRelativeZ": item.get("bailRelativeZ", 0),
            "bailRotation": item.get("bailRotation", 0),
        }

        scad_content = generate_scad_script(**params)

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".scad", delete=False
        ) as scad_file:
            scad_file.write(scad_content)
            scad_path = scad_file.name

        stl_path = scad_path.replace(".scad", ".stl")

        cmd = ["openscad", "-o", stl_path, "--export-format", "binstl", scad_path]

        env = os.environ.copy()
        env["DISPLAY"] = ":99"

        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=180, env=env
        )

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
        for item in order["items"]:
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
# Email 系統（使用 Resend）
# ==========================================


def send_customer_confirmation_email(order_data):
    """Email 1: 給顧客的確認 Email"""
    try:
        customer_email = order_data["userInfo"]["email"]
        order_id = order_data["orderId"]
        logger.info(f"📧 發送顧客確認 Email: {customer_email}")

        html = generate_customer_email_html(order_data)

        send_smtp_email = sib_api_v3_sdk.SendSmtpEmail(
            sender={"name": SENDER_NAME, "email": SENDER_EMAIL},
            to=[{"email": customer_email}],
            subject=f"DUET 訂單確認 #{order_id}",
            html_content=html,
        )

        response = api_instance.send_transac_email(send_smtp_email)
        logger.info(f"✅ 顧客確認 Email 已發送: {response}")
        return True

    except ApiException as e:
        logger.error(f"❌ Brevo API 錯誤: {e.status} - {e.reason}")
        logger.error(f"❌ 詳細訊息: {e.body}")
        return False
    except Exception as e:
        logger.error(f"❌ 顧客 Email 發送失敗: {str(e)}")
        import traceback

        logger.error(f"❌ 錯誤堆疊: {traceback.format_exc()}")
        return False


def send_internal_order_email(order_data):
    """Email 2: 給內部的訂單通知（無 STL）"""
    try:
        order_id = order_data["orderId"]
        logger.info(f"📧 發送內部訂單通知")

        html = generate_internal_order_email_html(order_data)

        send_smtp_email = sib_api_v3_sdk.SendSmtpEmail(
            sender={"name": SENDER_NAME, "email": SENDER_EMAIL},
            to=[{"email": INTERNAL_EMAIL}],
            subject=f"新訂單通知 - 訂單 #{order_id}",
            html_content=html,
        )

        response = api_instance.send_transac_email(send_smtp_email)
        logger.info(f"✅ 內部訂單 Email 已發送: {response}")
        return True

    except ApiException as e:
        logger.error(f"❌ Brevo API 錯誤: {e.status} - {e.reason}")
        logger.error(f"❌ 詳細訊息: {e.body}")
        return False
    except Exception as e:
        logger.error(f"❌ 內部訂單 Email 發送失敗: {str(e)}")
        import traceback

        logger.error(f"❌ 錯誤堆疊: {traceback.format_exc()}")
        return False


def send_internal_stl_email(order_data, stl_files):
    """Email 3: 給內部的 STL 完成通知（帶 STL）"""
    try:
        order_id = order_data["orderId"]
        logger.info(f"📧 發送內部 STL Email")

        html = generate_internal_stl_email_html(order_data)

        # 準備附件 - 將所有 STL 壓縮成一個 ZIP
        import zipfile
        import io

        if not stl_files:
            logger.warning("⚠️ 沒有 STL 檔案可以發送")
            return False

        # 創建 ZIP 檔案（在記憶體中）
        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
            for stl_path in stl_files:
                if os.path.exists(stl_path):
                    filename = os.path.basename(stl_path)
                    zip_file.write(stl_path, filename)
                    logger.info(f"📎 已壓縮: {filename}")

        # 轉換為 Base64
        zip_buffer.seek(0)
        zip_content = base64.b64encode(zip_buffer.read()).decode()
        zip_filename = f"STL_Files_{order_id}.zip"

        logger.info(f"📦 ZIP 檔案大小: {len(zip_content)} bytes (Base64)")

        # 發送 Email
        send_smtp_email = sib_api_v3_sdk.SendSmtpEmail(
            sender={"name": SENDER_NAME, "email": SENDER_EMAIL},
            to=[{"email": INTERNAL_EMAIL}],
            subject=f"STL 已生成 - 訂單 #{order_id}",
            html_content=html,
            attachment=[{"name": zip_filename, "content": zip_content}],
        )

        response = api_instance.send_transac_email(send_smtp_email)
        logger.info(f"✅ 內部 STL Email 已發送: {response}")
        return True

    except ApiException as e:
        logger.error(f"❌ Brevo API 錯誤: {e.status} - {e.reason}")
        logger.error(f"❌ 詳細訊息: {e.body}")
        return False
    except Exception as e:
        logger.error(f"❌ 內部 STL Email 發送失敗: {str(e)}")
        import traceback

        logger.error(f"❌ 錯誤堆疊: {traceback.format_exc()}")
        return False


# ==========================================
# Email HTML 模板
# ==========================================


def generate_customer_email_html(order_data):
    """顧客確認 Email HTML"""
    items_html = ""
    for idx, item in enumerate(order_data["items"], 1):
        items_html += f"""
        <tr>
            <td>{idx}</td>
            <td>{item['letter1']} + {item['letter2']}</td>
            <td>{item.get('font1', 'N/A')} + {item.get('font2', 'N/A')}</td>
            <td>{item.get('size', 'N/A')} mm</td>
            <td>{item.get('material', 'N/A')}</td>
            <td>{item.get('quantity', 1)}</td>
        </tr>
        """

    user_info = order_data["userInfo"]

    # 處理收件人資訊（支援新舊格式）
    recipient_name = user_info.get("recipientName", user_info.get("name", "N/A"))
    recipient_phone = user_info.get("recipientPhone", user_info.get("phone", "N/A"))
    shipping_address = user_info.get("shippingAddress", user_info.get("address", "N/A"))
    postal_code = user_info.get("postalCode", "")

    # 發票資訊
    invoice_type = user_info.get("invoiceType", "personal")
    invoice_html = ""
    if invoice_type == "company":
        invoice_html = f"""
        <p><strong>發票類型：</strong>公司發票（三聯式）</p>
        <p><strong>統一編號：</strong>{user_info.get('companyTaxId', 'N/A')}</p>
        <p><strong>公司抬頭：</strong>{user_info.get('companyName', 'N/A')}</p>
        """
    else:
        invoice_html = "<p><strong>發票類型：</strong>個人發票（二聯式）</p>"

    # 優惠碼資訊
    promo_html = ""
    if order_data.get("promoCode"):
        promo_html = f"""
        <div style="background: #e8f5e9; padding: 15px; border-radius: 5px; margin: 10px 0;">
            <p style="margin: 0;"><strong>✅ 已使用優惠碼：</strong>{order_data['promoCode']}</p>
            <p style="margin: 5px 0 0 0; font-size: 14px; color: #666;">{order_data.get('promoDescription', '')}</p>
        </div>
        """

    html = f"""
    <!DOCTYPE html>
    <html>
    <head><meta charset="UTF-8"><style>
        body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
        .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
        .header {{ background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 20px; text-align: center; border-radius: 5px; }}
        .section {{ background: #f9f9f9; padding: 15px; border-radius: 5px; margin: 15px 0; }}
        .section h3 {{ margin-top: 0; color: #333; border-bottom: 2px solid #ddd; padding-bottom: 10px; }}
        table {{ width: 100%; border-collapse: collapse; margin: 20px 0; }}
        th, td {{ padding: 10px; border: 1px solid #ddd; text-align: left; }}
        th {{ background: #f5f5f5; }}
        .total {{ font-size: 18px; font-weight: bold; color: #4CAF50; margin: 20px 0; }}
    </style></head>
    <body>
        <div class="container">
            <div class="header">
                <h1>✨ 訂單確認</h1>
            </div>
            
            <p>親愛的 {user_info.get('buyerName', user_info.get('name', '顧客'))} 您好，</p>
            <p>感謝您訂購 DUET 客製墜飾！您的訂單已確認。</p>
            
            {promo_html}
            
            <div class="section">
                <h3>📦 訂單編號</h3>
                <p>{order_data['orderId']}</p>
            </div>
            
            <div class="section">
                <h3>🛍️ 訂購商品</h3>
                <table>
                    <thead>
                        <tr>
                            <th>項目</th>
                            <th>字母組合</th>
                            <th>字體</th>
                            <th>尺寸</th>
                            <th>材質</th>
                            <th>數量</th>
                        </tr>
                    </thead>
                    <tbody>
                        {items_html}
                    </tbody>
                </table>
            </div>
            
            <div class="section">
                <h3>📋 購買人資訊</h3>
                <p><strong>姓名：</strong>{user_info.get('buyerName', user_info.get('name', 'N/A'))}</p>
                <p><strong>Email：</strong>{user_info.get('buyerEmail', user_info.get('email', 'N/A'))}</p>
                <p><strong>手機：</strong>{user_info.get('buyerPhone', user_info.get('phone', 'N/A'))}</p>
            </div>
            
            <div class="section">
                <h3>🚚 收件資訊</h3>
                <p><strong>收件人：</strong>{recipient_name}</p>
                <p><strong>收件電話：</strong>{recipient_phone}</p>
                <p><strong>郵遞區號：</strong>{postal_code if postal_code else '(未提供)'}</p>
                <p><strong>收貨地址：</strong>{shipping_address}</p>
            </div>
            
            <div class="section">
                <h3>🧾 發票資訊</h3>
                {invoice_html}
            </div>
            
            {'<div class="section"><h3>💬 備註</h3><p>' + user_info.get('note', '') + '</p></div>' if user_info.get('note') else ''}
            
            <div class="section">
                <h3>💰 訂單金額</h3>
                {f'<p><strong>原價：</strong>NT$ {order_data.get("originalTotal", order_data["total"]):,}</p>' if order_data.get('discount', 0) > 0 else ''}
                {f'<p style="color: #4CAF50;"><strong>優惠折扣：</strong>-NT$ {order_data.get("discount", 0):,}</p>' if order_data.get('discount', 0) > 0 else ''}
                <p class="total">應付金額：NT$ {order_data['total']:,}</p>
            </div>
            
            <p>我們將盡快為您製作產品，製作完成後會再次通知您。</p>
            
            <div style="background: #fff3cd; border-left: 4px solid #ffc107; padding: 15px; margin: 20px 0; border-radius: 5px;">
                <p style="margin: 0 0 10px 0; color: #856404;"><strong>⚠️ 重要提醒</strong></p>
                <p style="margin: 0 0 5px 0; color: #856404;">此為系統自動發送的確認信，請勿直接回覆此郵件。</p>
                <p style="margin: 0; color: #856404;">如有任何問題，請聯繫客服信箱：<a href="mailto:service@brendonchen.com" style="color: #667eea; text-decoration: none; font-weight: bold;">service@brendonchen.com</a></p>
            </div>
            
            <p>祝您有美好的一天！</p>
            <p><strong>DUET 團隊 敬上</strong></p>
        </div>
    </body>
    </html>
    """
    return html


def generate_internal_order_email_html(order_data):
    """內部訂單通知 Email HTML"""
    items_html = ""
    for idx, item in enumerate(order_data["items"], 1):
        items_html += f"""
        <tr>
            <td style="font-weight: bold;">{idx}</td>
            <td style="font-size: 11px;">{item['id']}</td>
            <td>{item['letter1']} + {item['letter2']}</td>
            <td style="font-size: 11px;">{item.get('font1', 'N/A')}<br>{item.get('font2', 'N/A')}</td>
            <td>{item.get('size', 'N/A')} mm</td>
            <td>{item.get('material', 'N/A')}</td>
            <td>{item.get('quantity', 1)}</td>
            <td>NT$ {item.get('price', 0):,}</td>
        </tr>
        <tr style="background: #f9f9f9;">
            <td colspan="8" style="padding: 10px; font-size: 11px;">
                <strong>🔧 技術參數：</strong><br>
                • 墜頭位置 (X/Y/Z): {item.get('bailRelativeX', 0):.2f} / {item.get('bailRelativeY', 0):.2f} / {item.get('bailRelativeZ', 0):.2f}<br>
                • 墜頭旋轉: {item.get('bailRotation', 0):.2f}°<br>
                • Letter1 BBox: W={item.get('letter1BBox', {}).get('width', 0):.2f} × H={item.get('letter1BBox', {}).get('height', 0):.2f} × D={item.get('letter1BBox', {}).get('depth', 0):.2f} mm<br>
                • Letter2 BBox: W={item.get('letter2BBox', {}).get('width', 0):.2f} × H={item.get('letter2BBox', {}).get('height', 0):.2f} × D={item.get('letter2BBox', {}).get('depth', 0):.2f} mm
            </td>
        </tr>
        """

    user_info = order_data["userInfo"]

    # 處理收件人資訊（支援新舊格式）
    buyer_name = user_info.get("buyerName", user_info.get("name", "N/A"))
    buyer_email = user_info.get("buyerEmail", user_info.get("email", "N/A"))
    buyer_phone = user_info.get("buyerPhone", user_info.get("phone", "N/A"))

    recipient_name = user_info.get("recipientName", user_info.get("name", "N/A"))
    recipient_phone = user_info.get("recipientPhone", user_info.get("phone", "N/A"))

    shipping_address = user_info.get("shippingAddress", user_info.get("address", "N/A"))
    postal_code = user_info.get("postalCode", "")

    # 發票資訊
    invoice_type = user_info.get("invoiceType", "personal")
    invoice_info = ""
    if invoice_type == "company":
        invoice_info = f"""
        <p><strong>發票類型：</strong>公司發票（三聯式）</p>
        <p><strong>統一編號：</strong>{user_info.get('companyTaxId', 'N/A')}</p>
        <p><strong>公司抬頭：</strong>{user_info.get('companyName', 'N/A')}</p>
        """
    else:
        invoice_info = "<p><strong>發票類型：</strong>個人發票（二聯式）</p>"

    # 優惠碼資訊
    promo_info = ""
    if order_data.get("promoCode"):
        promo_info = f"""
        <div style="background: #fff3cd; padding: 10px; border-left: 4px solid #ffc107; margin: 10px 0;">
            <p style="margin: 0;"><strong>✅ 使用優惠碼：</strong>{order_data['promoCode']}</p>
            <p style="margin: 5px 0 0 0; font-size: 12px;">{order_data.get('promoDescription', '')}</p>
        </div>
        """

    # 備註
    note_info = ""
    if user_info.get("note"):
        note_info = f"""
        <div style="background: #e3f2fd; padding: 10px; border-left: 4px solid #2196F3; margin: 10px 0;">
            <p style="margin: 0;"><strong>💬 客戶備註：</strong></p>
            <p style="margin: 5px 0 0 0;">{user_info.get('note')}</p>
        </div>
        """

    html = f"""
    <!DOCTYPE html>
    <html>
    <head><meta charset="UTF-8"><style>
        body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
        .container {{ max-width: 1000px; margin: 0 auto; padding: 20px; }}
        .header {{ background: #2196F3; color: white; padding: 20px; text-align: center; border-radius: 5px; }}
        table {{ width: 100%; border-collapse: collapse; margin: 20px 0; }}
        th, td {{ padding: 8px; border: 1px solid #ddd; text-align: left; font-size: 12px; }}
        th {{ background: #f5f5f5; font-weight: bold; }}
        .info-section {{ background: #f9f9f9; padding: 15px; border-radius: 5px; margin: 15px 0; }}
        .info-section h3 {{ margin-top: 0; color: #2196F3; border-bottom: 2px solid #ddd; padding-bottom: 5px; }}
        .amount {{ font-size: 18px; font-weight: bold; color: #4CAF50; }}
        .urgent {{ background: #ffebee; border-left: 4px solid #f44336; padding: 10px; margin: 10px 0; }}
    </style></head>
    <body>
        <div class="container">
            <div class="header">
                <h1>🆕 新訂單通知</h1>
                <p style="margin: 5px 0 0 0; font-size: 14px;">請確認訂單資訊並準備生產</p>
            </div>
            
            <div class="info-section">
                <h3>📋 訂單資訊</h3>
                <p><strong>訂單編號：</strong>{order_data['orderId']}</p>
                <p><strong>訂單時間：</strong>{order_data.get('timestamp', 'N/A')}</p>
                <p><strong>訂單狀態：</strong>✅ 已付款</p>
            </div>
            
            {promo_info}
            
            <div class="info-section">
                <h3>💰 金額明細</h3>
                {f'<p><strong>原價：</strong>NT$ {order_data.get("originalTotal", order_data["total"]):,}</p>' if order_data.get('discount', 0) > 0 else ''}
                {f'<p style="color: #4CAF50;"><strong>優惠折扣：</strong>-NT$ {order_data.get("discount", 0):,}</p>' if order_data.get('discount', 0) > 0 else ''}
                <p class="amount">應付金額：NT$ {order_data['total']:,}</p>
            </div>
            
            <div class="urgent">
                <p style="margin: 0;"><strong>⚠️ 出貨資訊（重要）</strong></p>
            </div>
            
            <div class="info-section">
                <h3>👤 購買人資訊</h3>
                <p><strong>姓名：</strong>{buyer_name}</p>
                <p><strong>Email：</strong>{buyer_email}</p>
                <p><strong>電話：</strong>{buyer_phone}</p>
            </div>
            
            <div class="info-section">
                <h3>📦 收件資訊</h3>
                <p><strong>收件人：</strong>{recipient_name}</p>
                <p><strong>收件電話：</strong>{recipient_phone}</p>
                <p><strong>郵遞區號：</strong>{postal_code if postal_code else '(未提供)'}</p>
                <p><strong>收貨地址：</strong>{shipping_address}</p>
            </div>
            
            <div class="info-section">
                <h3>🧾 發票資訊</h3>
                {invoice_info}
            </div>
            
            {note_info}
            
            <div class="info-section">
                <h3>🛍️ 訂單明細（生產參數）</h3>
                <table>
                    <thead>
                        <tr>
                            <th>項</th>
                            <th>商品 ID</th>
                            <th>字母</th>
                            <th>字體</th>
                            <th>尺寸</th>
                            <th>材質</th>
                            <th>數量</th>
                            <th>單價</th>
                        </tr>
                    </thead>
                    <tbody>
                        {items_html}
                    </tbody>
                </table>
            </div>
            
            <p style="background: #fff9c4; padding: 10px; border-radius: 5px;"><strong>📌 下一步：</strong>STL 檔案生成完成後會另外發送。</p>
        </div>
    </body>
    </html>
    """
    return html


def generate_internal_stl_email_html(order_data):
    """內部 STL 完成通知 Email HTML"""
    items_html = ""
    for idx, item in enumerate(order_data["items"], 1):
        items_html += f"""
        <tr>
            <td style="font-weight: bold;">{idx}</td>
            <td style="font-size: 11px;">{item['id']}.stl</td>
            <td>{item['letter1']} + {item['letter2']}</td>
            <td style="font-size: 11px;">{item.get('font1', 'N/A')}<br>{item.get('font2', 'N/A')}</td>
            <td>{item.get('size', 'N/A')} mm</td>
            <td>{item.get('material', 'N/A')}</td>
            <td>{item.get('quantity', 1)}</td>
        </tr>
        <tr style="background: #f0f8ff;">
            <td colspan="7" style="padding: 10px; font-size: 11px;">
                <strong>🔧 生產參數：</strong><br>
                • 墜頭位置 (X/Y/Z): {item.get('bailRelativeX', 0):.2f} / {item.get('bailRelativeY', 0):.2f} / {item.get('bailRelativeZ', 0):.2f}<br>
                • 墜頭旋轉: {item.get('bailRotation', 0):.2f}°<br>
                • Letter1 BBox: W={item.get('letter1BBox', {}).get('width', 0):.2f} × H={item.get('letter1BBox', {}).get('height', 0):.2f} × D={item.get('letter1BBox', {}).get('depth', 0):.2f} mm<br>
                • Letter2 BBox: W={item.get('letter2BBox', {}).get('width', 0):.2f} × H={item.get('letter2BBox', {}).get('height', 0):.2f} × D={item.get('letter2BBox', {}).get('depth', 0):.2f} mm
            </td>
        </tr>
        """

    user_info = order_data["userInfo"]

    # 處理收件人資訊（支援新舊格式）
    buyer_name = user_info.get("buyerName", user_info.get("name", "N/A"))
    recipient_name = user_info.get("recipientName", user_info.get("name", "N/A"))
    recipient_phone = user_info.get("recipientPhone", user_info.get("phone", "N/A"))
    shipping_address = user_info.get("shippingAddress", user_info.get("address", "N/A"))
    postal_code = user_info.get("postalCode", "")

    # 發票資訊
    invoice_type = user_info.get("invoiceType", "personal")
    invoice_info = ""
    if invoice_type == "company":
        invoice_info = f"""
        <p><strong>發票類型：</strong>公司發票（三聯式）</p>
        <p><strong>統一編號：</strong>{user_info.get('companyTaxId', 'N/A')}</p>
        <p><strong>公司抬頭：</strong>{user_info.get('companyName', 'N/A')}</p>
        """
    else:
        invoice_info = "<p><strong>發票類型：</strong>個人發票（二聯式）</p>"

    # 備註
    note_info = ""
    if user_info.get("note"):
        note_info = f"""
        <div style="background: #e3f2fd; padding: 10px; border-left: 4px solid #2196F3; margin: 10px 0;">
            <p style="margin: 0;"><strong>💬 客戶備註：</strong></p>
            <p style="margin: 5px 0 0 0;">{user_info.get('note')}</p>
        </div>
        """

    html = f"""
    <!DOCTYPE html>
    <html>
    <head><meta charset="UTF-8"><style>
        body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
        .container {{ max-width: 1000px; margin: 0 auto; padding: 20px; }}
        .header {{ background: #4CAF50; color: white; padding: 20px; text-align: center; border-radius: 5px; }}
        table {{ width: 100%; border-collapse: collapse; margin: 20px 0; }}
        th, td {{ padding: 8px; border: 1px solid #ddd; text-align: left; font-size: 12px; }}
        th {{ background: #f5f5f5; font-weight: bold; }}
        .info-section {{ background: #f9f9f9; padding: 15px; border-radius: 5px; margin: 15px 0; }}
        .info-section h3 {{ margin-top: 0; color: #4CAF50; border-bottom: 2px solid #ddd; padding-bottom: 5px; }}
        .urgent {{ background: #ffebee; border-left: 4px solid #f44336; padding: 10px; margin: 10px 0; font-weight: bold; }}
    </style></head>
    <body>
        <div class="container">
            <div class="header">
                <h1>✅ STL 檔案已完成</h1>
                <p style="margin: 5px 0 0 0; font-size: 14px;">請下載後進行生產並準備出貨</p>
            </div>
            
            <div class="info-section">
                <h3>📋 訂單資訊</h3>
                <p><strong>訂單編號：</strong>{order_data['orderId']}</p>
                <p><strong>訂單金額：</strong>NT$ {order_data['total']:,}</p>
                <p><strong>購買人：</strong>{buyer_name}</p>
            </div>
            
            <div class="urgent">
                <p style="margin: 0;">⚠️ 請確認出貨地址和發票資訊</p>
            </div>
            
            <div class="info-section">
                <h3>📦 出貨資訊</h3>
                <p><strong>收件人：</strong>{recipient_name}</p>
                <p><strong>收件電話：</strong>{recipient_phone}</p>
                <p><strong>郵遞區號：</strong>{postal_code if postal_code else '(未提供)'}</p>
                <p><strong>收貨地址：</strong>{shipping_address}</p>
            </div>
            
            <div class="info-section">
                <h3>🧾 發票資訊</h3>
                {invoice_info}
            </div>
            
            {note_info}
            
            <div class="info-section">
                <h3>📄 STL 檔案列表（含生產參數）</h3>
                <table>
                    <thead>
                        <tr>
                            <th>項</th>
                            <th>檔案名稱</th>
                            <th>字母</th>
                            <th>字體</th>
                            <th>尺寸</th>
                            <th>材質</th>
                            <th>數量</th>
                        </tr>
                    </thead>
                    <tbody>
                        {items_html}
                    </tbody>
                </table>
            </div>
            
            <div style="background: #e8f5e9; padding: 15px; border-radius: 5px; margin: 20px 0;">
                <p style="margin: 0;"><strong>✅ 所有 STL 檔案已附加在此郵件中</strong></p>
                <p style="margin: 5px 0 0 0; font-size: 13px;">請下載後進行生產，完成後依照上述地址出貨</p>
            </div>
        </div>
    </body>
    </html>
    """
    return html


# ==========================================
# STL 生成 API
# ==========================================


@app.route("/api/generate-stl", methods=["POST"])
def generate_stl():
    """生成 STL"""
    try:
        data = request.json
        logger.info(f"🔨 收到 STL 生成請求")

        # 只傳送 scad_generator 需要的 9 個參數
        params = {
            "letter1": data["letter1"],
            "letter2": data["letter2"],
            "font1": data["font1"],
            "font2": data["font2"],
            "size": data.get("size", 15),
            "bailRelativeX": data.get("bailRelativeX", 0),
            "bailRelativeY": data.get("bailRelativeY", 0),
            "bailRelativeZ": data.get("bailRelativeZ", 0),
            "bailRotation": data.get("bailRotation", 0),
        }

        scad_content = generate_scad_script(**params)

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".scad", delete=False
        ) as scad_file:
            scad_file.write(scad_content)
            scad_path = scad_file.name

        stl_path = scad_path.replace(".scad", ".stl")

        cmd = ["openscad", "-o", stl_path, "--export-format", "binstl", scad_path]

        env = os.environ.copy()
        env["DISPLAY"] = ":99"

        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=180, env=env
        )

        try:
            os.unlink(scad_path)
        except:
            pass

        if result.returncode != 0:
            logger.error(f"❌ OpenSCAD 錯誤: {result.stderr}")
            return jsonify({"success": False, "error": result.stderr}), 500

        if not os.path.exists(stl_path):
            logger.error("❌ STL 檔案不存在")
            return jsonify({"success": False, "error": "STL file not generated"}), 500

        logger.info(f"✅ STL 生成成功: {stl_path}")

        return send_file(
            stl_path,
            as_attachment=True,
            download_name=f"{data['letter1']}_{data['letter2']}.stl",
        )

    except Exception as e:
        logger.error(f"❌ STL 生成錯誤: {str(e)}")
        return jsonify({"success": False, "error": str(e)}), 500


# ==========================================
# 綠界金流
# ==========================================


def prepare_custom_fields(order_data):
    """準備 CustomField（訂單備份到綠界）- 使用簡單字符串"""
    try:
        items = order_data.get("items", [])
        user_info = order_data.get("userInfo", {})

        # CustomField1: 基本訂單信息（用 _ 分隔）
        field1 = "_".join(
            [
                str(order_data.get("orderId", "")),
                str(user_info.get("name", "")),
                str(user_info.get("email", "")),
                str(user_info.get("phone", "")),
                str(order_data.get("total", 0)),
            ]
        )[:200]

        # CustomField2-4: 商品信息（用 _ 分隔）
        def compress_item(item):
            # 字体名称空格替换成 _
            font1 = str(item.get("font1", "")).replace(" ", "_")
            font2 = str(item.get("font2", "")).replace(" ", "_")

            return "_".join(
                [
                    str(item.get("letter1", "")),
                    str(item.get("letter2", "")),
                    font1,
                    font2,
                    str(item.get("size", 15)),
                    str(item.get("material", "gold18k")),
                    str(round(item.get("bailRelativeX", 0))),
                    str(round(item.get("bailRelativeY", 0))),
                    str(round(item.get("bailRelativeZ", 0))),
                    str(round(item.get("bailRotation", 0))),
                ]
            )[:200]

        field2 = compress_item(items[0]) if len(items) > 0 else ""
        field3 = compress_item(items[1]) if len(items) > 1 else ""
        field4 = compress_item(items[2]) if len(items) > 2 else ""

        return {
            "CustomField1": field1,
            "CustomField2": field2,
            "CustomField3": field3,
            "CustomField4": field4,
        }
    except Exception as e:
        logger.error(f"❌ 準備 CustomField 失敗: {e}")
        return {}


@app.route("/api/validate-promo", methods=["POST"])
def validate_promo():
    """驗證優惠碼（前端即時驗證用）"""
    try:
        data = request.json
        promo_code = data.get("promoCode", "")
        total = data.get("total", 0)

        is_valid, discount, promo_info, error_msg = validate_promo_code(
            promo_code, total
        )

        if is_valid:
            return jsonify(
                {
                    "success": True,
                    "valid": True,
                    "discount": discount,
                    "finalTotal": total - discount,
                    "description": promo_info.get("description", ""),
                    "discountType": promo_info.get("type", ""),
                }
            )
        else:
            return jsonify({"success": True, "valid": False, "error": error_msg})

    except Exception as e:
        logger.error(f"❌ 優惠碼驗證錯誤: {str(e)}")
        return jsonify({"success": False, "error": str(e)}), 500


def generate_check_mac_value(params, hash_key, hash_iv, is_callback=False):
    """產生綠界 CheckMacValue

    Args:
        params: 參數字典
        hash_key: HashKey
        hash_iv: HashIV
        is_callback: 是否為回調驗證（True=回調，False=發送）
    """
    if is_callback:
        # 回調驗證：不過濾空值！綠界會發送空的 CustomField、StoreID
        filtered_params = params
    else:
        # 發送時：過濾空值
        filtered_params = {k: v for k, v in params.items() if v}

    sorted_params = sorted(filtered_params.items())

    # 1. 參數按字母排序並用 & 連接
    param_str = "&".join([f"{k}={v}" for k, v in sorted_params])

    # 2. 前面加 HashKey，後面加 HashIV
    raw_str = f"HashKey={hash_key}&{param_str}&HashIV={hash_iv}"

    # 3. URL encode
    encoded_str = urllib.parse.quote_plus(raw_str)

    # 4. 轉小寫
    encoded_str = encoded_str.lower()

    # 5. 特殊字符替換
    encoded_str = encoded_str.replace("%2d", "-")
    encoded_str = encoded_str.replace("%5f", "_")
    encoded_str = encoded_str.replace("%2e", ".")
    encoded_str = encoded_str.replace("%21", "!")
    encoded_str = encoded_str.replace("%2a", "*")
    encoded_str = encoded_str.replace("%28", "(")
    encoded_str = encoded_str.replace("%29", ")")

    if is_callback:
        logger.info(f"🔐 待簽名字串（回調）: {raw_str}")
    else:
        logger.info(f"🔐 待簽名字串（原始）: {raw_str}")
    logger.info(f"🔐 待簽名字串（編碼）: {encoded_str}")

    # 6. SHA256 加密
    check_mac = hashlib.sha256(encoded_str.encode("utf-8")).hexdigest()

    # 7. 轉大寫
    check_mac = check_mac.upper()

    logger.info(f"🔐 CheckMacValue: {check_mac}")
    return check_mac


@app.route("/api/checkout", methods=["POST"])
def checkout():
    """初始化綠界支付"""
    try:
        data = request.json
        logger.info(f"💳 收到結帳請求: {data.get('orderId')}")

        order_id = data["orderId"]
        original_total = data["total"]
        items = data["items"]
        user_info = data["userInfo"]
        promo_code = data.get("promoCode", "")
        ai_consultation = data.get("aiConsultation", None)  # ✅ 新增：接收 AI 諮詢資料
        return_url = data.get("returnUrl", request.host_url + "payment-success")

        # ✅ 後端驗證優惠碼（安全性必須）
        is_valid, discount, promo_info, error_msg = validate_promo_code(
            promo_code, original_total
        )

        if promo_code and not is_valid:
            logger.warning(f"❌ 優惠碼驗證失敗: {promo_code}, 原因: {error_msg}")
            return jsonify({"success": False, "error": error_msg or "優惠碼無效"}), 400

        # 計算最終金額
        final_total = original_total - discount

        logger.info(
            f"💰 原始金額: NT$ {original_total}, 折扣: NT$ {discount}, 最終金額: NT$ {final_total}"
        )

        order_data = {
            "orderId": order_id,
            "originalTotal": original_total,  # 記錄原始金額
            "discount": discount,  # 記錄折扣金額
            "total": final_total,  # 最終付款金額
            "promoCode": promo_code if is_valid else "",  # 記錄使用的優惠碼
            "promoDescription": promo_info.get("description", "") if promo_info else "",
            "items": items,
            "userInfo": user_info,
            "aiConsultation": ai_consultation,  # ✅ 新增：儲存 AI 諮詢資料
            "status": "pending",
            "timestamp": datetime.now().isoformat(),
            "testMode": False,
        }
        save_order(order_id, order_data)

        # 準備 CustomField（訂單備份）
        custom_fields = prepare_custom_fields(order_data)

        # 取得前端 URL（從環境變數或使用預設值）
        frontend_url = os.getenv("FRONTEND_URL", "https://www.brendonchen.com/duet")
        # 取得後端 URL
        backend_url = request.host_url.rstrip("/")

        payment_params = {
            "MerchantID": ECPAY_CONFIG["MerchantID"],
            "MerchantTradeNo": order_id,
            "MerchantTradeDate": datetime.now().strftime("%Y/%m/%d %H:%M:%S"),
            "PaymentType": "aio",
            "TotalAmount": str(int(final_total)),  # ✅ 使用折扣後的金額
            "TradeDesc": "DUET",
            "ItemName": "Pendant",
            "ReturnURL": backend_url + "/api/payment/callback",
            "OrderResultURL": backend_url
            + f"/api/payment/result?order={order_id}",  # ✅ 指向後端處理
            "ClientBackURL": frontend_url,  # ✅ 手動返回按鈕
            "ChoosePayment": "Credit",
            "EncryptType": "1",
            # **custom_fields  # 暂时注释，等验证逻辑修正后再启用
        }

        check_mac_value = generate_check_mac_value(
            payment_params, ECPAY_CONFIG["HashKey"], ECPAY_CONFIG["HashIV"]
        )
        payment_params["CheckMacValue"] = check_mac_value

        form_fields = "".join(
            [
                f'<input type="hidden" name="{k}" value="{v}">'
                for k, v in payment_params.items()
            ]
        )
        form_html = f'<form id="ecpay-form" method="post" action="{ECPAY_CONFIG["PaymentURL"]}">{form_fields}</form>'

        logger.info(f"✅ 綠界表單已生成，包含 CustomField 備份")

        return jsonify(
            {
                "success": True,
                "paymentFormHTML": form_html,
                "orderId": order_id,
                "finalTotal": final_total,  # 返回最終金額給前端確認
                "discount": discount,
            }
        )
    except Exception as e:
        logger.error(f"❌ 結帳錯誤: {str(e)}")
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/payment/callback", methods=["POST"])
def payment_callback():
    """綠界支付回調"""
    try:
        data = request.form.to_dict()
        logger.info(f"📥 收到綠界回調: {data.get('MerchantTradeNo')}")

        # DEBUG: 顯示所有原始參數
        logger.info(f"🔍 DEBUG - 所有參數:")
        for k, v in sorted(data.items()):
            logger.info(f"   {k}={v}")

        # ✅ 詳細記錄 CustomField 內容（用於測試）
        logger.info(f"📦 CustomField1: {data.get('CustomField1', '(empty)')}")
        logger.info(f"📦 CustomField2: {data.get('CustomField2', '(empty)')}")
        logger.info(f"📦 CustomField3: {data.get('CustomField3', '(empty)')}")
        logger.info(f"📦 CustomField4: {data.get('CustomField4', '(empty)')}")

        received_check_mac = data.pop("CheckMacValue", "")
        calculated_check_mac = generate_check_mac_value(
            data, ECPAY_CONFIG["HashKey"], ECPAY_CONFIG["HashIV"], is_callback=True
        )  # 回調驗證

        logger.info(f"📨 綠界發來的 CheckMacValue: {received_check_mac}")
        logger.info(f"🔢 我們計算的 CheckMacValue: {calculated_check_mac}")

        if received_check_mac != calculated_check_mac:
            logger.error(f"❌ CheckMacValue 驗證失敗！")
            logger.error(f"   收到: {received_check_mac}")
            logger.error(f"   計算: {calculated_check_mac}")
            return "0|CheckMacValue Error"

        logger.info("✅ CheckMacValue 驗證通過")

        if data.get("RtnCode") == "1":
            order_id = data["MerchantTradeNo"]
            logger.info(f"✅ 訂單 {order_id} 付款成功")
            process_order_after_payment(order_id, data)
            return "1|OK"
        else:
            order_id = data.get("MerchantTradeNo")
            if order_id:
                update_order_status(order_id, "payment_failed", data)
            return "0|Payment Failed"
    except Exception as e:
        logger.error(f"❌ 回調處理錯誤: {str(e)}")
        return "0|Error"


@app.route("/api/payment/result", methods=["POST"])
def payment_result():
    """處理 OrderResultURL 回調（綠界付款完成後的前端跳轉）"""
    try:
        # 接收綠界的 POST 資料
        data = request.form.to_dict()
        order_id = request.args.get("order")  # 從 URL 參數取得 order_id

        logger.info(f"🎯 收到 OrderResultURL 回調: {order_id}")
        logger.info(
            f"📦 付款結果資料: RtnCode={data.get('RtnCode')}, RtnMsg={data.get('RtnMsg')}"
        )

        # 驗證 CheckMacValue
        received_check_mac = data.pop("CheckMacValue", "")
        calculated_check_mac = generate_check_mac_value(
            data, ECPAY_CONFIG["HashKey"], ECPAY_CONFIG["HashIV"], is_callback=True
        )

        if received_check_mac != calculated_check_mac:
            logger.error(f"❌ OrderResultURL CheckMacValue 驗證失敗")
            # 即使驗證失敗，仍然導向前端（讓前端自己查詢訂單狀態）
            frontend_url = os.getenv("FRONTEND_URL", "https://www.brendonchen.com/duet")
            return f"""
                <html>
                <head><meta charset="utf-8"></head>
                <body>
                    <script>
                        window.location.href = "{frontend_url}?order={order_id}&verify_failed=true";
                    </script>
                </body>
                </html>
            """

        # 驗證成功，根據付款狀態導向前端
        if data.get("RtnCode") == "1":
            logger.info(f"✅ OrderResultURL 付款成功，準備導向前端")
            frontend_url = os.getenv("FRONTEND_URL", "https://duet.brendonchen.com")

            # 使用 URL 參數（GitHub Pages 不會過濾）
            return f"""
                <html>
                <head><meta charset="utf-8"></head>
                <body>
                    <h2>付款成功！正在導向...</h2>
                    <script>
                        window.location.href = "{frontend_url}?payment_success=true&order={order_id}";
                    </script>
                </body>
                </html>
            """
        else:
            logger.warning(f"⚠️ OrderResultURL 付款失敗: {data.get('RtnMsg')}")
            frontend_url = os.getenv("FRONTEND_URL", "https://duet.brendonchen.com")
            return f"""
                <html>
                <head><meta charset="utf-8"></head>
                <body>
                    <h2>付款失敗</h2>
                    <script>
                        window.location.href = "{frontend_url}?payment_failed=true&order={order_id}";
                    </script>
                </body>
                </html>
            """

    except Exception as e:
        logger.error(f"❌ OrderResultURL 處理錯誤: {str(e)}")
        # 錯誤時也導向前端
        frontend_url = os.getenv("FRONTEND_URL", "https://www.brendonchen.com/duet")
        return f"""
            <html>
            <head><meta charset="utf-8"></head>
            <body>
                <script>
                    window.location.href = "{frontend_url}?payment_error=true";
                </script>
            </body>
            </html>
        """


def process_order_after_payment(order_id, payment_data):
    """付款成功後處理訂單（非同步）"""
    try:
        order = load_order(order_id)
        if not order:
            logger.error(f"❌ 找不到訂單: {order_id}")
            return False

        # 1. 立即更新訂單狀態（同步）
        update_order_status(order_id, "paid", payment_data)

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


@app.route("/api/test-order", methods=["POST"])
def test_order():
    """測試模式：模擬訂單處理（非同步）"""
    try:
        data = request.json
        order_id = data.get("orderId")
        logger.info(f"🧪 測試模式訂單: {order_id}")

        # 立即儲存訂單（同步）
        save_order(order_id, data)

        # 更新訂單狀態
        update_order_status(order_id, "test_processing")

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
        return jsonify(
            {
                "success": True,
                "message": "測試訂單已處理，Email 已發送，STL 正在背景生成",
            }
        )

    except Exception as e:
        logger.error(f"❌ 測試訂單錯誤: {str(e)}")
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/payment-success")
def payment_success():
    """支付成功頁面"""
    return """<!DOCTYPE html><html><head><meta charset="UTF-8"><title>支付成功 - DUET</title>
    <style>body{font-family:Arial;display:flex;justify-content:center;align-items:center;height:100vh;
    margin:0;background:linear-gradient(135deg,#667eea 0%,#764ba2 100%)}.container{background:white;
    padding:40px;border-radius:15px;text-align:center;box-shadow:0 10px 40px rgba(0,0,0,0.2)}
    .success-icon{font-size:60px;color:#4CAF50;margin-bottom:20px}h1{color:#333;margin-bottom:10px}
    p{color:#666;line-height:1.6}.btn{display:inline-block;margin-top:20px;padding:12px 30px;
    background:#667eea;color:white;text-decoration:none;border-radius:5px}</style>
    <script>
    // ✅ 立即執行（不等待 DOM）
    console.log('💳 payment-success 頁面已載入');
    console.log('💾 設置 localStorage 標記');
    
    try {
        localStorage.setItem('duet_payment_success', 'true');
        console.log('✅ localStorage 設置成功:', localStorage.getItem('duet_payment_success'));
    } catch (e) {
        console.error('❌ localStorage 設置失敗:', e);
    }
    
    // ✅ 3 秒後跳轉
    console.log('⏰ 將在 3 秒後跳轉...');
    setTimeout(() => {
        console.log('🔄 開始跳轉到 DUET 頁面');
        window.location.href = 'https://duet.brendonchen.com';
    }, 3000);
    </script>
    </head>
    <body><div class="container"><div class="success-icon">✅</div><h1>支付成功！</h1>
    <p>感謝您的訂購！</p><p>確認信已發送至您的信箱。</p><p>正在返回設計頁面...</p>
    <p style="font-size:12px;color:#999;margin-top:20px;">如果沒有自動跳轉，請<a href="https://duet.brendonchen.com" style="color:#667eea;">點擊這裡</a></p>
    </div></body></html>"""


# ==========================================
# 測試端點
# ==========================================


@app.route("/api/test-custom-fields", methods=["POST"])
def test_custom_fields():
    """測試 CustomField 生成結果"""
    try:
        data = request.json
        logger.info("🧪 測試 CustomField 生成")

        custom_fields = prepare_custom_fields(data)

        # 解析並美化顯示
        import json as json_lib

        result = {}
        for key, value in custom_fields.items():
            try:
                parsed = json_lib.loads(value) if value else {}
                result[key] = {"raw": value, "parsed": parsed, "length": len(value)}
            except:
                result[key] = {
                    "raw": value,
                    "parsed": None,
                    "length": len(value) if value else 0,
                }

        logger.info(f"✅ CustomField1 長度: {result['CustomField1']['length']}/200")
        logger.info(f"✅ CustomField2 長度: {result['CustomField2']['length']}/200")
        logger.info(f"✅ CustomField3 長度: {result['CustomField3']['length']}/200")
        logger.info(f"✅ CustomField4 長度: {result['CustomField4']['length']}/200")

        return jsonify({"success": True, "customFields": result})

    except Exception as e:
        logger.error(f"❌ 測試錯誤: {str(e)}")
        return jsonify({"success": False, "error": str(e)}), 500


# ==========================================
# 健康檢查
# ==========================================


@app.route("/health")
def health():
    """健康檢查"""
    return jsonify({"status": "ok", "timestamp": datetime.now().isoformat()})


# ==========================================
# 初始化（Gunicorn 會執行這裡）
# ==========================================

logger.info("🚀 DUET Backend 初始化中...")
logger.info(f"📧 Email 服務: Resend")
logger.info(f"📧 發件人: {SENDER_EMAIL}")
logger.info(f"📧 內部收件: {INTERNAL_EMAIL}")
logger.info(f"💳 綠界: {ECPAY_CONFIG['MerchantID']}")

# 啟動背景 Worker
start_background_worker()
# ===== 在現有路由後面添加以下新端點 =====

# ============================================================
# AI 諮詢對話 API（修正版 - 替換到 app.py）
# ============================================================


@app.route("/api/ai-consultant", methods=["POST"])
def chat():
    """
    AI 諮詢對話 API
    """
    try:
        data = request.json
        user_message = data.get("message", "")
        conversation_history = data.get("history", [])

        # 構建訊息
        messages = conversation_history + [{"role": "user", "content": user_message}]

        # 呼叫 Claude API
        response = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=2000,
            system=SYSTEM_PROMPT,
            messages=messages,
        )

        ai_response = response.content[0].text

        # 判斷是否完成（只有當輸出 JSON 時才算完成）
        is_json_response = False
        result = None

        try:
            # 檢查是否是 JSON 回應
            json_str = ai_response.strip()

            # 必須以 { 或 ```json 開頭才可能是 JSON
            if (
                json_str.startswith("{")
                or json_str.startswith("```json")
                or json_str.startswith("```")
            ):
                # 清理 Markdown 標記
                if json_str.startswith("```json"):
                    json_str = json_str[7:]
                if json_str.startswith("```"):
                    json_str = json_str[3:]
                if json_str.endswith("```"):
                    json_str = json_str[:-3]
                json_str = json_str.strip()

                # 嘗試解析
                parsed = json.loads(json_str)

                # 檢查是否包含推薦欄位（這才是真正的完成標誌）
                if "recommendations" in parsed and "letters" in parsed:
                    is_json_response = True
                    result = parsed

                    # 確保有 conversationSummary
                    if "conversationSummary" not in result:
                        result["conversationSummary"] = {}

                    logger.info("✅ 檢測到完整 JSON 推薦，對話完成")
                else:
                    logger.info("⚠️ JSON 但缺少推薦欄位，繼續對話")
                    is_json_response = False

        except (json.JSONDecodeError, ValueError) as e:
            # 不是 JSON 或解析失敗，繼續對話
            logger.info(f"📝 對話進行中（非 JSON 回應）")
            is_json_response = False

        # 回傳結果
        if is_json_response and result:
            # 完成推薦
            return jsonify({"completed": True, "message": ai_response, **result})
        else:
            # 繼續對話
            return jsonify({"completed": False, "message": ai_response})

    except Exception as e:
        logger.error(f"❌ Chat API 錯誤: {str(e)}")
        logger.error(f"錯誤詳情: {traceback.format_exc()}")
        return (
            jsonify(
                {
                    "completed": False,
                    "message": "抱歉，發生了一些問題。請重新整理頁面再試一次。",
                    "error": str(e),
                }
            ),
            500,
        )


@app.route("/api/generate-design-concept", methods=["POST"])
def api_generate_design_concept():
    """
    生成設計理念端點
    基於對話歷史和最終選擇的字體
    """
    try:
        data = request.json

        # 獲取必要參數
        conversation = data.get("conversation", [])
        selected_fonts = data.get("selectedFonts", {})
        items = data.get("items", [])

        if not conversation or not selected_fonts or not items:
            return jsonify({"success": False, "error": "缺少必要參數"}), 400

        # 從第一個 item 獲取字母
        first_item = items[0]
        letters = {
            "letter1": first_item.get("letter1", ""),
            "letter2": first_item.get("letter2", ""),
        }

        # 使用實際選定的字體（不是推薦的字體）
        final_fonts = {
            "font1": first_item.get("font1", selected_fonts.get("font1", "")),
            "font2": first_item.get("font2", selected_fonts.get("font2", "")),
        }

        # 生成設計理念
        result = generate_design_concept(conversation, final_fonts, letters)

        if result["success"]:
            return jsonify(
                {"success": True, "concept": result["concept"], "items": items}
            )
        else:
            return (
                jsonify({"success": False, "error": result.get("error", "生成失敗")}),
                500,
            )

    except Exception as e:
        print(f"Design Concept API Error: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/order/status/<order_id>", methods=["GET"])
def get_order_status(order_id):
    """
    快速查詢訂單付款狀態（用於前端付款檢測）
    """
    try:
        order = load_order(order_id)
        if not order:
            return jsonify({"success": False, "error": "訂單不存在"}), 404

        return jsonify(
            {
                "success": True,
                "order_id": order_id,
                "status": order.get("status", "unknown"),
                "paid": order.get("status") == "paid",
            }
        )
    except Exception as e:
        logger.error(f"❌ 查詢訂單狀態錯誤: {str(e)}")
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/order/<order_id>", methods=["GET"])
def get_order(order_id):
    """
    獲取訂單詳情
    用於設計理念生成頁面
    """
    try:
        # 從 Google Sheets 查詢訂單
        creds_dict = json.loads(GOOGLE_CREDENTIALS_JSON)
        gc = gspread.service_account_from_dict(creds_dict)
        sheet = gc.open_by_key(SHEETS_ID).sheet1

        # 查找訂單
        orders = sheet.get_all_records()
        order = None

        for row in orders:
            if row.get("訂單編號") == order_id:
                order = row
                break

        if not order:
            return jsonify({"success": False, "error": "訂單不存在"}), 404

        # 解析訂單項目（從多個欄位合併）
        items = []
        # Google Sheets 的商品存在 E, F, G 欄（商品1, 商品2, 商品3）
        for i in range(1, 4):  # 最多 3 個商品
            item_str = order.get(f"商品{i}", "")
            if item_str:
                try:
                    items.append(json.loads(item_str))
                except:
                    pass

        # 獲取 AI 諮詢數據（M 欄）
        ai_data_str = order.get("AI諮詢資料", "")  # 使用中文欄位名
        ai_data = json.loads(ai_data_str) if ai_data_str else None

        return jsonify(
            {
                "success": True,
                "order_id": order_id,
                "customer": {
                    "name": order.get("姓名", ""),
                    "email": order.get("Email", ""),
                },
                "items": items,
                "ai_data": ai_data,
                "status": order.get("狀態", ""),
                "needs_design_concept": order.get("needs_design_concept", False),
            }
        )

    except Exception as e:
        print(f"Get Order Error: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/save-design-concepts", methods=["POST"])
def save_design_concepts():
    """
    保存設計理念和卡片選擇
    """
    try:
        data = request.json
        order_id = data.get("order_id")
        concepts = data.get("concepts", [])

        if not order_id or not concepts:
            return jsonify({"success": False, "error": "缺少必要參數"}), 400

        # 更新訂單記錄
        gc = gspread.service_account_from_dict(json.loads(GOOGLE_CREDENTIALS_JSON))
        sheet = gc.open_by_key(SHEETS_ID).sheet1

        # 找到訂單行
        cell = sheet.find(order_id)
        if cell:
            row_index = cell.row

            # 更新設計理念數據
            concepts_json = json.dumps(concepts, ensure_ascii=False)

            # 假設有 "design_concepts" 欄位
            sheet.update_cell(row_index, 15, concepts_json)  # 調整欄位索引

            # 發送確認郵件（包含設計理念）
            send_order_confirmation_with_concepts(order_id, concepts)

            return jsonify({"success": True, "message": "設計理念已保存"})
        else:
            return jsonify({"success": False, "error": "找不到訂單"}), 404

    except Exception as e:
        print(f"Save Design Concepts Error: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


def send_order_confirmation_with_concepts(order_id, concepts):
    """
    發送包含設計理念的訂單確認郵件
    """
    try:
        # 獲取訂單詳情
        gc = gspread.service_account_from_dict(json.loads(GOOGLE_CREDENTIALS_JSON))
        sheet = gc.open_by_key(SHEETS_ID).sheet1

        orders = sheet.get_all_records()
        order = None

        for row in orders:
            if row.get("訂單編號") == order_id:
                order = row
                break

        if not order:
            print(f"Order {order_id} not found")
            return

        # 構建郵件內容
        concepts_html = ""
        for concept in concepts:
            concepts_html += f"""
            <div style="margin: 30px 0; padding: 20px; background: #f9f9f9; border-left: 4px solid #d4af37;">
                <h3 style="color: #d4af37;">{concept['design_signature']}</h3>
                <p style="line-height: 1.8; color: #333;">{concept['concept_text']}</p>
                <p style="color: #888; font-size: 14px;">卡片版型：{concept['card_template']}</p>
            </div>
            """

        email_html = f"""
        <html>
        <body style="font-family: 'Microsoft JhengHei', sans-serif; padding: 20px;">
            <h1 style="color: #d4af37;">DUET 訂單確認</h1>
            <p>親愛的 {order.get('姓名', '')}，</p>
            <p>感謝您訂購 DUET 訂製珠寶！</p>
            
            <h2>您的專屬設計理念</h2>
            {concepts_html}
            
            <p>我們會將設計理念印製成精美卡片，隨作品一起送達。</p>
            
            <p style="margin-top: 40px; color: #888;">
                如有任何問題，請直接回覆此郵件。<br>
                DUET by BCAG
            </p>
        </body>
        </html>
        """

        # 使用 Resend 發送
        import resend

        resend.api_key = os.getenv("RESEND_API_KEY")

        resend.Emails.send(
            {
                "from": "service@brendonchen.com",
                "to": [order.get("Email", "")],
                "subject": f"DUET 訂單確認 #{order_id}",
                "html": email_html,
            }
        )

        print(f"Confirmation email sent for order {order_id}")

    except Exception as e:
        print(f"Send Email Error: {e}")


# ===== CORS 設定更新（如果需要） =====
# 確保 CORS 允許前端域名訪問
# 在現有 CORS 設定中添加：
# origins=["https://brendonchen.com", "http://localhost:3000"]

# ==========================================
# 本地開發用
# ==========================================
# ============================================================
# 設計理念生成 API（新增到 app.py）
# ============================================================


@app.route("/api/design-story", methods=["POST"])
def generate_design_story():
    """
    結帳後生成設計理念
    請求格式：
    {
        "conversationSummary": {...},  // 從初次諮詢取得
        "selectedFonts": {
            "letter1": "B",
            "font1": "Cormorant Garamond",
            "letter2": "R",
            "font2": "Jost"
        },
        "fontReason": "我覺得 Cormorant Garamond 很優雅..."
    }
    """
    try:
        data = request.json

        conversation_summary = data.get("conversationSummary", {})
        selected_fonts = data.get("selectedFonts", {})
        font_reason = data.get("fontReason", "")

        # DEBUG: 檢查接收到的資料
        logger.info(f"🔍 設計理念生成請求:")
        logger.info(f"  - conversationSummary 類型: {type(conversation_summary)}")
        logger.info(
            f"  - conversationSummary 內容: {json.dumps(conversation_summary, ensure_ascii=False)[:200]}"
        )
        logger.info(f"  - fontReason: {font_reason[:100]}")

        # 提取關鍵資訊
        conversation_history = conversation_summary.get("conversationHistory", [])
        ai_summary = conversation_summary.get("summary", "")
        full_recommendations = conversation_summary.get("fullRecommendations", {})

        # 將對話歷史轉換為易讀格式
        conversation_text = ""
        for msg in conversation_history:
            role = "AI 顧問" if msg.get("role") == "assistant" else "顧客"
            content = msg.get("content", "")
            conversation_text += f"{role}：{content}\n\n"

        # 獲取字體推薦理由
        letter1_recommendations = full_recommendations.get("letter1", [])
        letter2_recommendations = full_recommendations.get("letter2", [])

        # 找出用戶選擇的字體及其推薦理由
        selected_font1_reason = ""
        selected_font2_reason = ""

        for rec in letter1_recommendations:
            if rec.get("font") == selected_fonts.get("font1"):
                selected_font1_reason = rec.get("reason", "")
                break

        for rec in letter2_recommendations:
            if rec.get("font") == selected_fonts.get("font2"):
                selected_font2_reason = rec.get("reason", "")
                break

        # 構建清晰的提示詞
        messages = [
            {
                "role": "user",
                "content": f"""請根據以下資訊，生成溫暖、有故事感的設計理念（2-3段，每段30-50字）：

=== 完整的諮詢對話 ===
{conversation_text}

=== AI 顧問的總結 ===
{ai_summary}

=== 選擇的字母與字體 ===
• 字母 {selected_fonts.get('letter1', '')}: {selected_fonts.get('font1', '')}
  推薦理由：{selected_font1_reason}

• 字母 {selected_fonts.get('letter2', '')}: {selected_fonts.get('font2', '')}
  推薦理由：{selected_font2_reason}

=== 顧客對字體選擇的說明 ===
{font_reason}

=== 任務 ===
請整合上述所有內容，特別是：
1. 對話中提到的故事、回憶、轉折點
2. 兩人的關係特質與共通點
3. 字體選擇的情感意義
4. 配戴時想傳達的情感

生成能打動人心的設計理念（2-3段）。直接輸出文字，不要包含任何格式標記。""",
            }
        ]

        # 呼叫 Claude API
        response = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=1000,
            system=SYSTEM_PROMPT,  # 會使用第六階段邏輯
            messages=messages,
        )

        design_story = response.content[0].text.strip()

        return jsonify({"success": True, "designStory": design_story})

    except json.JSONDecodeError as e:
        logger.error(f"❌ JSON 解析失敗: {str(e)}")
        logger.error(f"原始回應: {ai_response}")
        return jsonify({"success": False, "error": f"JSON 解析失敗: {str(e)}"}), 500

    except Exception as e:
        logger.error(f"❌ 設計理念生成錯誤: {str(e)}")
        return jsonify({"success": False, "error": str(e)}), 500


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
