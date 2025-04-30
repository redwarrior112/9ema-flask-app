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
BASE_URL = "https://paper-api.alpaca.markets"  # Change to live URL for live trading

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

    # Build base order
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

    timestamp = datetime.utcnow().isoformat()
    print(f"📩 [{timestamp}] New trade: {action.upper()} {qty}x {ticker}")

    try:
        alpaca_url = f"{BASE_URL}/v2/orders"
        response = requests.post(alpaca_url, json=order, headers=HEADERS)
        response.raise_for_status()
        result = response.json()

        print("🛰️ Alpaca Response (Success):")
        print(json.dumps(result, indent=2))

        with open("trades_log.csv", "a") as f:
            f.write(f"{timestamp},{ticker},{action},{qty},{use_oco},{take_profit},{stop_loss}\n")

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
