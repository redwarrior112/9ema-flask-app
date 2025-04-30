from flask import Flask, request, jsonify
import requests
import os
from dotenv import load_dotenv

load_dotenv()  # ✅ Load .env variables

app = Flask(__name__)

# 🔐 Load secrets from .env
ALPACA_API_KEY = os.getenv("ALPACA_API_KEY")
ALPACA_SECRET_KEY = os.getenv("ALPACA_SECRET_KEY")
SHARED_SECRET = os.getenv("SHARED_SECRET")

BASE_URL = 'https://paper-api.alpaca.markets'
HEADERS = {
    'APCA-API-KEY-ID': ALPACA_API_KEY,
    'APCA-API-SECRET-KEY': ALPACA_SECRET_KEY
}


@app.route('/webhook', methods=['POST'])
def webhook():
    from flask import request, jsonify
    import os

    SHARED_SECRET = os.getenv("SHARED_SECRET")
    data = request.json

    if not data:
        return jsonify({"error": "Missing JSON"}), 400

    if data.get("secret") != SHARED_SECRET:
        return jsonify({"error": "Unauthorized"}), 403

    # Process logic (minimal test return)
    return jsonify({"status": "success", "message": "Webhook received."})

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
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 10000)))

