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

BASE_URL = "https://paper-api.alpaca.markets"
HEADERS = {
    "APCA-API-KEY-ID": ALPACA_API_KEY,
    "APCA-API-SECRET-KEY": ALPACA_SECRET_KEY
}

# === App setup ===
app = Flask(__name__)
last_entry_time = None
position_limit = 2

# === CSV Logging Function ===
def log_trade_csv(ticker, action, qty, price, pnl, timestamp):
    file_path = "trade_log.csv"
    file_exists = os.path.isfile(file_path)
    with open(file_path, mode="a", newline="") as file:
        writer = csv.writer(file)
        if not file_exists:
            writer.writerow(["Timestamp", "Ticker", "Action", "Qty", "Price", "PnL"])
        writer.writerow([timestamp, ticker, action, qty, price, pnl])

# === Home Page ===
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
            raise ValueError("No data parsed")
    except Exception as e:
        print("❌ JSON parsing failed:", str(e))
        return jsonify({"error": "Invalid JSON", "details": str(e)}), 400

    if data.get("secret") != SHARED_SECRET:
        return jsonify({"error": "Unauthorized"}), 403

    # === Parse fields from webhook JSON ===
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

    # === Log to CSV ===
    log_trade_csv(ticker, action, qty, price, pnl, timestamp)

    # === Check current position size ===
    position_resp = requests.get(f"{BASE_URL}/v2/positions/{ticker}", headers=HEADERS)
    current_position = 0
    if position_resp.status_code == 200:
        position_data = position_resp.json()
        current_position = int(float(position_data.get("qty", 0)))

    if action == "buy":
        now = datetime.utcnow().replace(second=0, microsecond=0)
        if last_entry_time == now:
            return jsonify({"status": "skipped", "reason": "Already entered this bar"})
        if current_position >= position_limit:
            return jsonify({"status": "skipped", "reason": "Position limit reached"})
        last_entry_time = now

    if action == "sell" and current_position == 0:
        return jsonify({"status": "skipped", "reason": "No position to exit"})

    # === Build order for Alpaca ===
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

    # === Submit order to Alpaca ===
    try:
        response = requests.post(f"{BASE_URL}/v2/orders", json=order, headers=HEADERS)
        response.raise_for_status()
        result = response.json()

        print("🛰️ Alpaca Response:", json.dumps(result, indent=2))

        # === Optional: Send Discord Notification ===
        if DISCORD_WEBHOOK_URL:
            color = 3066993 if action == "buy" else 15158332
            emoji = "🚀" if action == "buy" else "🔻"
            type_label = "Entry" if action == "buy" else "Trailing Exit"

            embed = {
                "title": f"{emoji} {action.upper()} {qty}x {ticker}",
                "color": color,
                "fields": [
                    {"name": "Price", "value": f"${price:.2f}", "inline": True},
                    {"name": "PnL", "value": f"${pnl:.2f}", "inline": True},
                    {"name": "Time", "value": timestamp, "inline": True},
                    {"name": "Type", "value": type_label, "inline": True}
                ],
                "timestamp": timestamp
            }
            discord_payload = {"embeds": [embed]}
            requests.post(DISCORD_WEBHOOK_URL, json=discord_payload)

        return jsonify({"status": "success", "alpaca_response": result})

    except requests.exceptions.HTTPError as http_err:
        print("❌ Alpaca HTTP Error:", http_err)
        print("🧾 Alpaca Response Text:", response.text)
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

# === Run Flask App ===
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 10000)))
