from flask import Flask, request, jsonify
import requests

app = Flask(__name__)

# ✅ Alpaca API credentials
ALPACA_API_KEY = "PKFJHEKY307EBXAKHY1H"
ALPACA_SECRET_KEY = "bO5TmyDXN2g9rczJinhGSPngSoz3og4Ma4cNU2bo"
# Trading API base
BASE_URL = "https://paper-api.alpaca.markets"
# Data API base for quotes/trades
DATA_URL = "https://data.alpaca.markets/v2"

HEADERS = {
    'APCA-API-KEY-ID': ALPACA_API_KEY,
    'APCA-API-SECRET-KEY': ALPACA_SECRET_KEY
}

@app.route('/webhook', methods=['POST'])
def webhook():
    data = request.json
    print("📩 Webhook received:", data)

    ticker = data.get("ticker")
    action = data.get("action")
    qty = int(data.get("qty", 1))
    use_oco = data.get("use_oco", False)
    tp = data.get("take_profit")
    sl = data.get("stop_loss")

    if action not in ["buy", "sell"]:
        return jsonify({"error": "Invalid action"}), 400

    order_data = {
        "symbol": ticker,
        "qty": qty,
        "side": action,
        "type": "market",
        "time_in_force": "gtc"
    }

    if use_oco and tp and sl:
        order_data["type"] = "limit"
        order_data["limit_price"] = tp
        order_data["order_class"] = "bracket"
        order_data["take_profit"] = {"limit_price": tp}
        order_data["stop_loss"] = {"stop_price": sl}

    response = requests.post(f"{BASE_URL}/v2/orders", json=order_data, headers=HEADERS)
    print("🛰️ Alpaca response:", response.json())

    return jsonify(response.json())

if __name__ == '__main__':
    app.run(port=5000)
