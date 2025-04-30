from flask import Flask, request, jsonify
import os
import requests
import json
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)

ALPACA_API_KEY = os.getenv("ALPACA_API_KEY")
ALPACA_SECRET_KEY = os.getenv("ALPACA_SECRET_KEY")
SHARED_SECRET = os.getenv("SHARED_SECRET")
BASE_URL = "https://paper-api.alpaca.markets"  # Trading API base
DATA_URL = "https://data.alpaca.markets/v2"     # Data API base for quotes/trades
DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL")

HEADERS = {
    "APCA-API-KEY-ID": ALPACA_API_KEY,
    "APCA-API-SECRET-KEY": ALPACA_SECRET_KEY
}

@app.route("/", methods=["GET"])
def home():
    return "🚀 9EMA Webhook is Live and Trading"

@app.route("/status", methods=["GET"])
def status():
    return jsonify({
        "status": "online",
        "alpaca_key_loaded": bool(ALPACA_API_KEY),
        "timestamp": datetime.utcnow().isoformat()
    })

@app.route("/orders", methods=["GET"])
def orders():
    try:
        response = requests.get(f"{BASE_URL}/v2/orders", headers=HEADERS)
        response.raise_for_status()
        orders = response.json()
        return jsonify({"status": "success", "orders": orders})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route("/webhook", methods=["POST"])
def webhook():
    print("📩 Headers received:")
    print(dict(request.headers))

    print("📦 Raw body:")
    print(request.data)

    data = request.get_json(force=True, silent=True)

    if not data:
        print("❌ Invalid JSON — returning 400.")
        return jsonify({"error": "Missing or invalid JSON"}), 400

    if data.get("secret") != SHARED_SECRET:
        print("❌ Unauthorized: Secret mismatch.")
        return jsonify({"error": "Unauthorized"}), 403

    # Parse trade info
    ticker = data.get("ticker")
    action = data.get("action")
    qty = data.get("qty", 1)
    use_oco = data.get("use_oco", False)
    take_profit = data.get("take_profit")
    stop_loss = data.get("stop_loss")

    timestamp = datetime.utcnow().isoformat()
    print(f"📩 [{timestamp}] New trade: {action.upper()} {qty}x {ticker}")

    # Validate bracket order levels using Alpaca data API
    if use_oco and take_profit and stop_loss:
        try:
            quote_url = f"{DATA_URL}/stocks/{ticker}/quotes/latest"
            quote_response = requests.get(quote_url, headers=HEADERS)
            quote_response.raise_for_status()
            base_price = float(quote_response.json()["quote"]["ap"])
            print(f"🔎 Base price for {ticker}: {base_price}")

            if float(take_profit) <= base_price + 0.01:
                return jsonify({"error": "take_profit must be > base_price + 0.01", "base_price": base_price}), 400

            if float(stop_loss) >= base_price - 0.01:
                return jsonify({"error": "stop_loss must be < base_price - 0.01", "base_price": base_price}), 400

        except Exception as e:
            print("❌ Error retrieving market price:", str(e))
            return jsonify({"error": "Failed to retrieve market price", "details": str(e)}), 500

    # Build order
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
        alpaca_url = f"{BASE_URL}/v2/orders"
        response = requests.post(alpaca_url, json=order, headers=HEADERS)
        response.raise_for_status()
        result = response.json()

        print("🛰️ Alpaca Response (Success):")
        print(json.dumps(result, indent=2))

        with open("trades_log.csv", "a") as f:
            f.write(f"{timestamp},{ticker},{action},{qty},{use_oco},{take_profit},{stop_loss}\n")

        # Send to Discord with embedded format
        if DISCORD_WEBHOOK_URL:
            color = 3066993 if action.lower() == "buy" else 15158332
            embed = {
                "title": f"Trade Executed: {action.upper()} {qty}x {ticker}",
                "color": color,
                "fields": [
                    {"name": "Take Profit", "value": f"{take_profit}", "inline": True},
                    {"name": "Stop Loss", "value": f"{stop_loss}", "inline": True},
                    {"name": "Filled At", "value": result.get("filled_avg_price", "n/a"), "inline": True}
                ],
                "timestamp": timestamp
            }
            discord_payload = {"embeds": [embed]}

            try:
                requests.post(DISCORD_WEBHOOK_URL, json=discord_payload)
            except Exception as discord_err:
                print("⚠️ Failed to send Discord notification:", str(discord_err))

        return jsonify({
            "status": "success",
            "trade": {
                "ticker": ticker,
                "action": action,
                "qty": qty
            },
            "alpaca_response": result
        })

    except requests.exceptions.HTTPError as http_err:
        error_msg = response.json().get("message", str(http_err))
        print("❌ Alpaca HTTP Error:", error_msg)
        return jsonify({
            "status": "error",
            "message": "Alpaca API Error",
            "details": error_msg,
            "alpaca_code": response.status_code
        }), response.status_code

    except Exception as e:
        print("❌ Unexpected error:", str(e))
        return jsonify({
            "status": "error",
            "message": "Unhandled Exception",
            "details": str(e)
        }), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 10000)))
