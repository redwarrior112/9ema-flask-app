from flask import Flask, request, jsonify
import os
import requests
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

@app.route("/webhook", methods=["POST"])
def webhook():
    data = request.get_json()
    print("📩 Webhook received:", data)

    if not data:
        return jsonify({"error": "Missing JSON"}), 400

    if data.get("secret") != SHARED_SECRET:
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

    # Optional: OCO/bracket order logic
    if use_oco and take_profit and stop_loss:
        order["order_class"] = "bracket"
        order["take_profit"] = {"limit_price": float(take_profit)}
        order["stop_loss"] = {"stop_price": float(stop_loss)}

    # Send to Alpaca
    alpaca_url = f"{BASE_URL}/v2/orders"
    response = requests.post(alpaca_url, json=order, headers=HEADERS)

    print("🛰️ Alpaca response:", response.json())
    return jsonify(response.json())


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 10000)))

