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

# Desactiva TzCache para evitar errores en Render
yf.set_tz_cache_location(None)

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
    except Exception as e:
        logger.error(f"Error fetching exchange rates: {e}")
        return jsonify({"error": str(e)}), 500

@app.route("/yahoo")
def yahoo_quotes():
    symbols = request.args.get("symbols", "").split(",")
    result = {}
    
    # Procesa cada ticker individualmente para evitar fallos en batch
    for sym in symbols:
        sym = sym.strip()
        if not sym:
            continue
        try:
            ticker = yf.Ticker(sym)
            hist = ticker.history(period="6mo", interval="1d")
            
            if not hist.empty:
                closes = hist['Close']
                last = float(closes.iloc[-1])
                prev = float(closes.iloc[-2]) if len(closes) >= 2 else last
                chg_pct = round((last - prev) / prev * 100, 2) if prev != 0 else 0
                result[sym] = {
                    "price": round(last, 2),
                    "chg_pct": chg_pct
                }
            else:
                result[sym] = {"price": "—", "chg_pct": 0}
        except Exception as e:
            logger.warning(f"Ticker {sym} error: {e}")
            result[sym] = {"price": "—", "chg_pct": 0}
    
    return jsonify(result)

@app.route("/news")
def news():
    try:
        import feedparser
        feeds = [
            ("Reuters", "https://feeds.reuters.com/reuters/businessNews"),
            ("Bloomberg", "https://feeds.bloomberg.com/markets/news.rss"),
        ]
        items = []
        for source, url in feeds:
            try:
                feed = feedparser.parse(url)
                for entry in feed.entries[:3]:
                    items.append({
                        "source": source,
                        "title": entry.get('title', '')[:80],
                        "url": entry.get('link', ''),
                        "time": entry.get('published', '')[:10] if entry.get('published') else ''
                    })
                if len(items) >= 5:
                    break
            except:
                pass
        return jsonify(items[:5])
    except:
        return jsonify([])

@app.route("/sector_data")
def sector_data():
    tickers = request.args.get("tickers", "").split(",")
    tickers = [t.strip() for t in tickers if t.strip()]
    result = {}
    
    # Procesa cada ticker individualmente
    for ticker in tickers:
        try:
            t = yf.Ticker(ticker)
            hist = t.history(period="6mo", interval="1d")
            
            if not hist.empty:
                closes = hist['Close']
                hist_list = [
                    {"date": str(closes.index[i].date()), "close": round(float(closes.iloc[i]), 2)} 
                    for i in range(len(closes))
                ]
                last = float(closes.iloc[-1])
                prev = float(closes.iloc[0])
                chg_pct = round((last - prev) / prev * 100, 2) if prev != 0 else 0
                
                result[ticker] = {
                    "price": round(last, 2),
                    "chg_pct": chg_pct,
                    "history": hist_list
                }
        except Exception as e:
            logger.warning(f"Sector data {ticker} error: {e}")
    
    return jsonify(result)

@app.route("/status")
def status():
    return jsonify({"running": False})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
