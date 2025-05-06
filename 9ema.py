from flask import Flask, request, jsonify
import os
import requests
import json
import csv
from datetime import datetime
from dotenv import load_dotenv

# === Load environment variables ===
load_dotenv()
ALPACA_API_KEY = os.getenv("ALPACA_API_KEY")
ALPACA_SECRET_KEY = os.getenv("ALPACA_SECRET_KEY")
SHARED_SECRET = os.getenv("SHARED_SECRET")
DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL")
NOTION_TOKEN = os.getenv("NOTION_TOKEN")
NOTION_DATABASE_ID = os.getenv("NOTION_DATABASE_ID")

BASE_URL = "https://paper-api.alpaca.markets"
HEADERS = {
    "APCA-API-KEY-ID": ALPACA_API_KEY,
    "APCA-API-SECRET-KEY": ALPACA_SECRET_KEY
}

# === Flask App ===
app = Flask(__name__)
last_entry_time = None
position_limit = 2

# === CSV Logging ===
def log_trade_csv(ticker, action, qty, price, pnl, timestamp):
    file_path = "trade_log.csv"
    file_exists = os.path.isfile(file_path)
    with open(file_path, mode="a", newline="") as file:
        writer = csv.writer(file)
        if not file_exists:
            writer.writerow(["Timestamp", "Ticker", "Action", "Qty", "Price", "PnL"])
        writer.writerow([timestamp, ticker, action, qty, price, pnl])

import os
import requests

NOTION_TOKEN = os.getenv("NOTION_TOKEN")
NOTION_DATABASE_ID = os.getenv("NOTION_DATABASE_ID")

def log_trade_to_notion(ticker, action, qty, price, pnl, timestamp):
    url = "https://api.notion.com/v1/pages"
    headers = {
        "Authorization": f"Bearer {NOTION_TOKEN}",
        "Content-Type": "application/json",
        "Notion-Version": "2022-06-28"
    }

    payload = {
        "parent": { "database_id": NOTION_DATABASE_ID },
"properties": {
    "Ticker": {
        "title": [
            {
                "text": { "content": ticker }
            }
        ]
    },
    "Action": {
        "select": {
            "name": action  # Must match an existing option in your database
        }
    },
    "Qty": {
        "number": qty
    },
    "Price": {
        "number": price
    },
    "PnL": {
        "number": pnl
    },
    "Timestamp": {
        "date": { "start": timestamp }
    }
}
    }

    try:
        res = requests.post(url, headers=headers, json=payload)
        res.raise_for_status()
        print("✅ Trade logged to Notion")
    except Exception as e:
        print("❌ Notion logging failed:", e)
        print("📦 Response:", getattr(e.response, "text", "No response"))

# === Home Endpoint ===
@app.route("/", methods=["GET"])
def home():
    return "✅ You Can Accomplish Anything With A Solid Plan ;)"

# === Webhook Endpoint ===
@app.route("/webhook", methods=["POST"])
def webhook():
    global last_entry_time

    print("📩 Headers received:")
    print(dict(request.headers))
    print("📦 Raw body:")
    print(request.data)

    try:
        data = request.get_json(force=True)
        if not data:
            raise ValueError("No JSON received")
    except Exception as e:
        return jsonify({"error": "Invalid JSON", "details": str(e)}), 400

    if data.get("secret") != SHARED_SECRET:
        return jsonify({"error": "Unauthorized"}), 403

    # === Parse Payload ===
    ticker = data.get("ticker")
    action = data.get("action")
    qty = int(data.get("qty", 1))
    use_oco = data.get("use_oco", False)
    take_profit = data.get("take_profit")
    stop_loss = data.get("stop_loss")
    price = float(data.get("price", 0))
    pnl = float(data.get("pnl", 0))
    timestamp = datetime.utcnow().isoformat()

    print(f"📩 [{timestamp}] New trade: {action.upper()} {qty}x {ticker} @ {price} | PnL: {pnl}")

    # === Log to CSV & Notion ===
    log_trade_csv(ticker, action, qty, price, pnl, timestamp)
    log_trade_to_notion(ticker, action, qty, price, pnl, timestamp)

    # === Position Check ===
    current_position = 0
    try:
        pos_resp = requests.get(f"{BASE_URL}/v2/positions/{ticker}", headers=HEADERS)
        if pos_resp.status_code == 200:
            pos_data = pos_resp.json()
            current_position = int(float(pos_data.get("qty", 0)))
        elif pos_resp.status_code == 404:
            print(f"ℹ️ No open position for {ticker}")
    except Exception as e:
        print("❌ Failed to get position:", e)

    if action == "buy":
        now = datetime.utcnow().replace(second=0, microsecond=0)
        if last_entry_time == now:
            return jsonify({"status": "skipped", "reason": "Already entered this bar"})
        if current_position >= position_limit:
            return jsonify({"status": "skipped", "reason": "Position limit reached"})
        last_entry_time = now

    if action == "sell" and current_position == 0:
        return jsonify({"status": "skipped", "reason": "No position to exit"})

    # === Alpaca Order ===
    order = {
        "symbol": ticker,
        "qty": qty,
        "side": action,
        "type": "market",
        "time_in_force": "gtc"
    }

    if use_oco and take_profit and stop_loss:
        order["order_class"] = "bracket"
        order["take_profit"] = {"limit_price": float(take_profit)}
        order["stop_loss"] = {"stop_price": float(stop_loss)}

    try:
        response = requests.post(f"{BASE_URL}/v2/orders", json=order, headers=HEADERS)
        response.raise_for_status()
        result = response.json()
        print("🛰️ Alpaca Response:", json.dumps(result, indent=2))

        # === Discord Alert ===
        if DISCORD_WEBHOOK_URL:
            color = 3066993 if action == "buy" else 15158332
            emoji = "🚀" if action == "buy" else "🔻"
            embed = {
                "title": f"{emoji} {action.upper()} {qty}x {ticker}",
                "color": color,
                "fields": [
                    {"name": "Price", "value": f"${price:.2f}", "inline": True},
                    {"name": "PnL", "value": f"${pnl:.2f}", "inline": True},
                    {"name": "Time", "value": timestamp, "inline": True},
                    {"name": "Type", "value": "Entry" if action == "buy" else "Exit", "inline": True}
                ],
                "timestamp": timestamp
            }
            requests.post(DISCORD_WEBHOOK_URL, json={"embeds": [embed]})

        return jsonify({"status": "success", "alpaca_response": result})

    except requests.exceptions.HTTPError as http_err:
        print("❌ Alpaca HTTP error:", http_err)
        return jsonify({
            "status": "error",
            "message": "Alpaca API Error",
            "details": str(http_err),
            "response": response.text
        }), 500

    except Exception as e:
        print("❌ Unexpected error:", e)
        return jsonify({
            "status": "error",
            "message": "Webhook Execution Error",
            "details": str(e)
        }), 500

# === Start App ===
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 10000)))
