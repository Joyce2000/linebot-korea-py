from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, TextMessage, TextSendMessage
import requests
from datetime import datetime
import os
from dotenv import load_dotenv

load_dotenv()

LINE_CHANNEL_SECRET = os.getenv("LINE_CHANNEL_SECRET")
LINE_CHANNEL_ACCESS_TOKEN = os.getenv("LINE_CHANNEL_ACCESS_TOKEN")
WEBAPP_URL = os.getenv("GOOGLE_SHEET_WEBAPP_URL")
line_bot_api = LineBotApi(LINE_CHANNEL_ACCESS_TOKEN)
handler = WebhookHandler(LINE_CHANNEL_SECRET)

app = Flask(__name__)


# ===== 匯率查詢 =====
def get_krw_to_twd_rate():
    try:
        # 使用無需 API Key 的 Open Access 端點
        url = "https://open.er-api.com/v6/latest/KRW"
        res = requests.get(url, timeout=10)
        res.raise_for_status()
        data = res.json()
        # 檢查回傳結果
        if data.get("result") == "success" and "rates" in data:
            # 從 KRW 基底換算為 TWD
            rate = data["rates"].get("TWD")
            if rate is None:
                # 若 TWD 不在其中，跳 fallback
                raise ValueError("TWD rate missing in response")
            return rate
        else:
            raise ValueError(f"Unexpected API result: {data}")
    except Exception as e:
        print("匯率抓取失敗:", e)
        # fallback 值（你可以再調整此值）
        return 0.022


# ===== 記帳函數 =====
def add_expense(text):
    # 格式: 項目,金額,幣別
    try:
        item, amount, currency = text.split(",")
        amount = float(amount)
        currency = currency.upper()
        date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        rate = get_krw_to_twd_rate()

        if currency == "KRW":
            twd = round(amount * rate, 2)
            krw = amount
        else:
            twd = amount
            krw = round(amount / rate, 0)

        # 發送到 Google Apps Script
        payload = {
            "date": date,
            "item": item,
            "currency": currency,
            "twd": twd,
            "krw": krw,
        }
        if WEBAPP_URL:
            requests.post(WEBAPP_URL, json=payload)
        else:
            raise ValueError(
                "GOOGLE_SHEET_WEBAPP_URL environment variable is not set")

        return f"已記帳：{item} {amount} {currency}\n台幣: {twd} TWD\n韓元: {krw} KRW"
    except Exception as e:
        return f"記帳失敗，請確認格式: 項目,金額,幣別\n錯誤訊息: {str(e)}"


# ===== 韓元對照表函數 =====
def krw_to_twd_table():
    krw_list = [
        1000,
        11000,
        12000,
        13000,
        14000,
        15000,
        16000,
        17000,
        18000,
        19000,
        20000,
        25000,
        30000,
        35000,
        40000,
        45000,
        50000,
    ]
    rate = get_krw_to_twd_rate()
    result = "韓元→台幣對照表:\n"
    for krw in krw_list:
        twd = round(krw * rate, 2)
        result += f"{krw} KRW → {twd} TWD\n"
    result += "50000 KRW以上 → 請自行乘上匯率"
    return result


# ===== Line Bot 主程式 =====
@app.route("/", methods=["GET"])
def home():
    return "LINE Bot is running! Please use /callback for webhook."


@app.route("/callback", methods=["POST"])
def callback():
    signature = request.headers["X-Line-Signature"]
    body = request.get_data(as_text=True)
    
    # 記錄收到的請求內容
    print(f"Received webhook: {body}")

    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)
    return "OK"


@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    try:
        # 檢查是否為重發的訊息
        if hasattr(event, 'delivery_context') and event.delivery_context.is_redelivery:
            print("Ignoring redelivered message")
            return
        
        text = event.message.text.strip()

        if text.lower() == "對照表":
            reply = krw_to_twd_table()
        else:
            reply = add_expense(text)

        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=reply))
    except Exception as e:
        # 記錄錯誤但不中斷程式
        print(f"Error handling message: {str(e)}")


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
