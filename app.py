from flask import Flask, render_template, jsonify, request
import os
import requests
from datetime import datetime
import yfinance as yf
import pandas as pd
import pytz
import logging

app = Flask(__name__)
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/market_status")
def market_status():
    tz = pytz.timezone('America/New_York')
    now = datetime.now(tz)
    is_open = now.weekday() < 5 and 9.5 <= now.hour + now.minute/60 < 16
    return jsonify({"is_open": is_open})

@app.route("/exchange_rates")
def exchange_rates():
    try:
        response = requests.get("https://api.bluelytics.com.ar/json/blue_rate/last", timeout=5)
        data = response.json()
        return jsonify({
            "oficial": {"price": data.get("oficial", {}).get("value_sell", 0), "chg_pct": 0},
            "blue": {"price": data.get("blue", {}).get("value_sell", 0), "chg_pct": 0},
            "mep": {"price": data.get("mep", {}).get("value_sell", 0), "chg_pct": 0},
            "ccl": {"price": data.get("ccl", {}).get("value_sell", 0), "chg_pct": 0}
        })
    except:
        return jsonify({"error": "error"}), 500

@app.route("/yahoo")
def yahoo_quotes():
    symbols = request.args.get("symbols", "").split(",")
    result = {}
    try:
        data = yf.download(symbols, period="6mo", progress=False)
        closes = data["Close"] if "Close" in data else data
        for sym in symbols:
            sym = sym.strip()
            try:
                col = closes[sym] if sym in closes.columns else closes
                vals = col.dropna()
                if len(vals) >= 2:
                    result[sym] = {"price": round(float(vals.iloc[-1]), 2), "chg_pct": 0}
            except:
                pass
    except:
        pass
    return jsonify(result)

@app.route("/news")
def news():
    return jsonify([])

@app.route("/sector_data")
def sector_data():
    return jsonify({})

@app.route("/status")
def status():
    return jsonify({"running": False})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
