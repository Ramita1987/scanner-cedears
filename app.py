from flask import Flask, render_template, jsonify, request
import os
import json
from datetime import datetime
import pytz
import logging

app = Flask(__name__)
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Mock data para demostración
MOCK_PRICES = {
    'SPY': {'price': 485.50, 'chg_pct': 1.23},
    'QQQ': {'price': 384.25, 'chg_pct': 2.15},
    '^DJI': {'price': 38912.47, 'chg_pct': 0.87},
    '^RUT': {'price': 2056.08, 'chg_pct': 1.45},
    'BTC-USD': {'price': 62500.00, 'chg_pct': 3.25},
    'ETH-USD': {'price': 3250.00, 'chg_pct': 2.85},
    '^VIX': {'price': 14.32, 'chg_pct': -2.10},
    '^MERV': {'price': 1245.67, 'chg_pct': 0.56},
    'GC=F': {'price': 2385.50, 'chg_pct': 0.78},
    'CL=F': {'price': 82.45, 'chg_pct': 1.05},
}

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/market_status")
def market_status():
    tz = pytz.timezone('America/New_York')
    now = datetime.now(tz)
    is_open = now.weekday() < 5 and 9.5 <= now.hour + now.minute/60 < 16
    return jsonify({
        "is_open": is_open,
        "current_time_est": now.strftime("%Y-%m-%d %H:%M:%S"),
        "market_opens": "09:30",
        "market_closes": "16:00"
    })

@app.route("/exchange_rates")
def exchange_rates():
    return jsonify({
        "oficial": {"price": 850.50, "chg_pct": -0.15},
        "blue": {"price": 920.00, "chg_pct": 0.25},
        "mep": {"price": 895.75, "chg_pct": 0.10},
        "ccl": {"price": 898.30, "chg_pct": 0.12}
    })

@app.route("/yahoo")
def yahoo_quotes():
    symbols = request.args.get("symbols", "").split(",")
    result = {}
    for sym in symbols:
        sym = sym.strip()
        result[sym] = MOCK_PRICES.get(sym, {"price": 100.00, "chg_pct": 0.00})
    return jsonify(result)

@app.route("/news")
def news():
    return jsonify([
        {"source": "Reuters", "title": "Mercados suben ante datos positivos", "url": "#", "time": "2026-03-30 01:30"},
        {"source": "Infobae", "title": "Dólar retrocede en la apertura", "url": "#", "time": "2026-03-30 01:15"},
        {"source": "Bloomberg", "title": "Fed mantiene tasas sin cambios", "url": "#", "time": "2026-03-30 00:45"}
    ])

@app.route("/sector_data")
def sector_data():
    return jsonify({})

@app.route("/status")
def status():
    return jsonify({
        "running": False,
        "session": "",
        "progress": 0,
        "total": 0,
        "current_ticker": "",
        "results": [],
        "log": [],
        "last_run": None
    })

@app.route("/historial")
def historial():
    return jsonify([])

@app.route("/watchlist_data")
def watchlist_data():
    return jsonify({})

@app.route("/run/<session>", methods=["POST"])
def run(session):
    return jsonify({"ok": True, "session": session.upper()})

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
