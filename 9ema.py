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

app = Flask(__name__)
last_entry_time = None
position_limit = 2

def log_trade_csv(ticker, action, qty, price, pnl, timestamp):
    file_path = "trade_log.csv"
    file_exists = os.path.isfile(file_path)
    with open(file_path, mode="a", newline="") as file:
        writer = csv.writer(file)
        if not file_exists:
            writer.writerow(["Timestamp", "Ticker", "Action", "Qty", "Price", "PnL"])
        writer.writerow([timestamp, ticker, action, qty, price, pnl])

def log_trade_to_notion(ticker, action, qty, price, pnl, timestamp):
    url = "https://api.notion.com/v1/pages"
    headers = {
        "Authorization": f"Bearer {NOTION_TOKEN}",
        "Content-Type": "application/json",
        "Notion-Version": "2022-06-28"
    }

    payload = {
        "parent": {"database_id": NOTION_DATABASE_ID},
        "properties": {
            "Ticker": {"title": [{"text": {"content": ticker}}]},
            "Action": {"select": {"name": action}},
            "Qty": {"number": qty},
            "Price": {"number": price},
            "PnL": {"number": pnl},
            "Timestamp": {"date": {"start": timestamp}}
        }
    }

    try:
        res = requests.post(url, headers=headers, json=payload)
        res.raise_for_status()
        print("✅ Trade logged to Notion")
    except Exception as e:
        print("❌ Notion logging failed:", e)

# === Fetch latest price for capital-based sizing ===
def get_latest_price(symbol):
    try:
        quote_url = f"https://data.alpaca.markets/v2/stocks/{symbol}/quotes/latest"
        response = requests.get(quote_url, headers=HEADERS)
        response.raise_for_status()
        quote_data = response.json()
        ask_price = float(quote_data.get("quote", {}).get("ap"))
        return ask_price if ask_price > 0 else None
    except Exception as e:
        print(f"⚠️ Failed to fetch price for {symbol}: {e}")
        return None

@app.route("/", methods=["GET"])
def home():
    return "✅ You Can Accomplish Anything With A Solid Plan ;)"

@app.route("/webhook", methods=["POST"])
def webhook():
    global last_entry_time

    print("📩 Headers received:", dict(request.headers))
    print("📦 Raw body:", request.data)

    try:
        data = request.get_json(force=True)
        if not data:
            raise ValueError("No JSON received")
    except Exception as e:
        return jsonify({"error": "Invalid JSON", "details": str(e)}), 400

    if data.get("secret") != SHARED_SECRET:
        return jsonify({"error": "Unauthorized"}), 403

    ticker = data.get("ticker")
    action = data.get("action")
    use_oco = data.get("use_oco", False)
    take_profit = data.get("take_profit")
    stop_loss = data.get("stop_loss")
    price = float(data.get("price", 0))
    pnl = float(data.get("pnl", 0))
    timestamp = datetime.utcnow().isoformat()

    # Capital-Based Position Sizing
    target_capital = 500.0  # Example $500 allocation
    latest_price = get_latest_price(ticker)

    if latest_price:
        qty = max(int(target_capital // latest_price), 1)
        print(f"📊 Calculated Quantity: {qty} shares at ${latest_price:.2f} for target ${target_capital}")
    else:
        return jsonify({"error": "Failed to fetch latest price for quantity calculation"}), 500

    print(f"📩 [{timestamp}] New trade: {action.upper()} {qty}x {ticker} @ {price} | PnL: {pnl}")

    log_trade_csv(ticker, action, qty, price, pnl, timestamp)
    log_trade_to_notion(ticker, action, qty, price, pnl, timestamp)

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

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 10000)))
