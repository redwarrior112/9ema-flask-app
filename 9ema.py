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

    # Parse info
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

    # Check current position size
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
        response = requests.post(f"{BASE_URL}/v2/orders", json=order, headers=HEADERS)
        response.raise_for_status()
        result = response.json()

        print("🛰️ Alpaca Response:", json.dumps(result, indent=2))

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
        return jsonify({"status": "error", "message": "Webhook Execution Error", "details": str(e)}), 500
