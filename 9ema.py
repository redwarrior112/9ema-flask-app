from flask import Flask, request, jsonify
import os, requests, json, csv
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()
ALPACA_API_KEY = os.getenv("ALPACA_API_KEY")
ALPACA_SECRET_KEY = os.getenv("ALPACA_SECRET_KEY")
SHARED_SECRET = os.getenv("SHARED_SECRET")
DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL")
NOTION_TOKEN = os.getenv("NOTION_TOKEN")
NOTION_DATABASE_ID = os.getenv("NOTION_DATABASE_ID")

BASE_URL = "https://paper-api.alpaca.markets"
ORDER_URL = f"{BASE_URL}/v2/orders"
MARKET_URL = "https://data.alpaca.markets"

HEADERS = {
    "APCA-API-KEY-ID": ALPACA_API_KEY,
    "APCA-API-SECRET-KEY": ALPACA_SECRET_KEY
}

MARKET_HEADERS = HEADERS.copy()

app = Flask(__name__)
last_entry_time = None

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

def get_latest_price(symbol):
    try:
        url = f"{MARKET_URL}/v2/stocks/{symbol}/quotes/latest"
        response = requests.get(url, headers=MARKET_HEADERS)
        response.raise_for_status()
        data = response.json()
        ask_price = float(data.get("quote", {}).get("ap", 0))
        return ask_price if ask_price > 0 else None
    except Exception as e:
        print(f"⚠️ Failed to fetch price for {symbol}: {e}")
        return None

@app.route("/", methods=["GET"])
def home():
    return "✅ You Can Accomplish Anything With A Solid Plan ;)"

@app.route("/webhook", methods=["POST"])
def webhook():
    try:
        data = request.get_json(force=True)
        if not data:
            raise ValueError("No JSON received")
    except Exception as e:
        return jsonify({"error": "Invalid JSON", "details": str(e)}), 400

    if data.get("secret") != SHARED_SECRET:
        return jsonify({"error": "Unauthorized"}), 403

    try:
        ticker    = data.get("ticker")
        action    = data.get("action").lower()
        price     = float(data.get("price", 0))
        pnl       = float(data.get("pnl", 0))
        timestamp = datetime.utcnow().isoformat()
        use_oco   = data.get("use_oco", False)
        tp        = data.get("take_profit")
        sl        = data.get("stop_loss")

        latest_price = get_latest_price(ticker)
        if latest_price:
            target_capital = 1000.0
            qty = max(int(target_capital // latest_price), 1)
            print(f"📊 Using calculated qty: {qty} @ ${latest_price:.2f}")
        else:
            qty = int(data.get("qty", 1))
            print(f"⚠️ Falling back to TradingView qty: {qty}")

        log_trade_csv(ticker, action, qty, price, pnl, timestamp)
        log_trade_to_notion(ticker, action, qty, price, pnl, timestamp)

        order = {
            "symbol": ticker,
            "qty": qty,
            "side": action,
            "type": "market",
            "time_in_force": "gtc"
        }

        if use_oco and tp and sl:
            order["order_class"] = "bracket"
            order["take_profit"] = {"limit_price": float(tp)}
            order["stop_loss"]   = {"stop_price": float(sl)}

        response = requests.post(ORDER_URL, json=order, headers=HEADERS)
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
        return jsonify({
            "status": "error",
            "message": "Alpaca API Error",
            "details": str(http_err),
            "response": response.text
        }), 500

    except Exception as e:
        return jsonify({
            "status": "error",
            "message": "Webhook Execution Error",
            "details": str(e)
        }), 500

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 10000)))

