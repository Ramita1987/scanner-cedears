"""
╔══════════════════════════════════════════════════════════════╗
║         SCANNER CEDEARS — INTERFAZ WEB                      ║
║         Flask App para Render.com                           ║
╚══════════════════════════════════════════════════════════════╝
"""

from flask import Flask, render_template, jsonify, request
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
import threading
import json
import os
import sys
import requests
from datetime import datetime, timedelta
import yfinance as yf
import pandas as pd
import pytz
import logging

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

app = Flask(__name__)
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Estado global del scanner
scanner_state = {
    "running": False,
    "session": "",
    "progress": 0,
    "total": 0,
    "current_ticker": "",
    "results": [],
    "log": [],
    "last_run": None,
}

# Inicializar scheduler
scheduler = BackgroundScheduler(timezone='America/New_York')

def run_scanner_thread(session: str, params: dict = None, active_setups: list = None):
    """Corre el scanner en un thread separado para no bloquear la web."""
    global scanner_state

    scanner_state["running"]        = True
    scanner_state["session"]        = session
    scanner_state["progress"]       = 0
    scanner_state["results"]        = []
    scanner_state["log"]            = []
    scanner_state["current_ticker"] = ""

    try:
        import importlib
        import scanner as sc
        importlib.reload(sc)

        from config import CEDEARS, TOP_N, MIN_PROBABILITY

        mp = float(params.get("mp", MIN_PROBABILITY)) if params else MIN_PROBABILITY
        tn = int(params.get("tn", TOP_N))             if params else TOP_N

        scanner_state["total"] = len(CEDEARS)
        resultados = []

        for i, ticker in enumerate(CEDEARS, 1):
            scanner_state["progress"]       = i
            scanner_state["current_ticker"] = ticker

            try:
                res = sc.analizar_ticker(ticker, active_setups=active_setups)
                if res and res["probabilidad"] >= mp:
                    resultados.append(res)
                    scanner_state["log"].append(
                        f"✅ {ticker.replace('.BA','')} — {res['setup']} | {res['probabilidad']}%"
                    )
                else:
                    scanner_state["log"].append(f"⬜ {ticker.replace('.BA','')} — sin setup")
            except Exception as e:
                scanner_state["log"].append(f"⚠️ {ticker} — error")

            import time
            time.sleep(0.3) if i % 10 != 0 else time.sleep(2)

        resultados.sort(
            key=lambda x: (x["probabilidad"], x["confluencias"], x["vol_rel"]),
            reverse=True
        )
        top = resultados[:tn]
        scanner_state["results"]  = top
        scanner_state["last_run"] = datetime.now().strftime("%d/%m/%Y %H:%M")

        if top:
            sc.guardar_excel(top, session)

        msg = sc.build_telegram_message(top, session)
        sc.send_telegram(msg)

        scanner_state["log"].append(f"\n🏁 Completado. {len(top)} oportunidades encontradas.")

    except Exception as e:
        scanner_state["log"].append(f"❌ Error crítico: {e}")

    finally:
        scanner_state["running"] = False


def get_historial():
    """Lee el historial del Excel y lo retorna como lista."""
    try:
        from openpyxl import load_workbook
        archivo = os.path.join(os.path.dirname(os.path.abspath(__file__)), "registros_scanner.xlsx")
        if not os.path.exists(archivo):
            return []
        wb = load_workbook(archivo)
        ws = wb.active
        rows = []
        for row in ws.iter_rows(min_row=2, values_only=True):
            if row[0]:
                rows.append({
                    "fecha":        row[0],
                    "hora":         row[1],
                    "sesion":       row[2],
                    "ticker":       row[3],
                    "setup":        row[4],
                    "confluencias": row[5],
                    "probabilidad": row[6],
                    "precio":       row[7],
                    "target":       row[8],
                    "stop":         row[9],
                    "rsi":          row[10],
                    "vol_rel":      row[11],
                    "atr":          row[12],
                    "descripcion":  row[13],
                    "resultado":    row[14] if len(row) > 14 else "Pendiente",
                })
        return list(reversed(rows))
    except Exception:
        return []


# ═══════════════════════════════════════════════════════════════
#  RUTAS
# ═══════════════════════════════════════════════════════════════

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/run/<session>", methods=["POST"])
def run(session):
    """Arranca el scanner en background."""
    session = session.upper()
    if session not in ["PRE-MARKET", "APERTURA", "CIERRE", "MANUAL"]:
        return jsonify({"error": "Sesión inválida"}), 400

    if scanner_state["running"]:
        return jsonify({"error": "El scanner ya está corriendo"}), 400

    body = request.get_json(silent=True) or {}
    params = body.get("params", {})
    active_setups = body.get("active_setups", None)

    t = threading.Thread(
        target=run_scanner_thread,
        args=(session, params, active_setups),
        daemon=True
    )
    t.start()
    return jsonify({"ok": True, "session": session})


@app.route("/market_status")
def market_status():
    """Retorna si el mercado está abierto o cerrado."""
    tz = pytz.timezone('America/New_York')
    now = datetime.now(tz)
    
    is_open = (
        now.weekday() < 5 and 
        9.5 <= now.hour + now.minute/60 < 16
    )
    
    return jsonify({
        "is_open": is_open,
        "current_time_est": now.strftime("%Y-%m-%d %H:%M:%S"),
        "market_opens": "09:30",
        "market_closes": "16:00"
    })


@app.route("/news")
def news():
    """Retorna noticias en español."""
    import feedparser
    
    feeds = [
        ("Reuters Español", "https://feeds.reuters.com/reuters/businessNews"),
        ("Infobae", "https://www.infobae.com/feed/"),
        ("El Financiero", "https://www.elfinanciero.com.mx/feed/"),
    ]
    
    items = []
    for source, url in feeds:
        try:
            feed = feedparser.parse(url)
            for entry in feed.entries[:5]:
                items.append({
                    "source": source,
                    "title": entry.get('title', ''),
                    "url": entry.get('link', ''),
                    "time": entry.get('published', '')[:16] if entry.get('published') else ''
                })
            if len(items) >= 10:
                break
        except Exception as e:
            logger.error(f"Error fetching {source}: {e}")
    
    return jsonify(items[:5])


@app.route("/exchange_rates")
def exchange_rates():
    """Retorna tipos de cambio del dólar argentino."""
    try:
        response = requests.get("https://www.dolarito.ar/cotizacion/dolar-hoy", timeout=5)
        response.encoding = 'utf-8'
        
        # Parse HTML - búsqueda simple de valores
        html = response.text
        
        result = {}
        
        # Intentar extraer valores básicos (esto es un scrape simple)
        if "oficial" in html.lower():
            result["oficial"] = {"price": 0, "chg_pct": 0}
        if "blue" in html.lower():
            result["blue"] = {"price": 0, "chg_pct": 0}
        if "mep" in html.lower():
            result["mep"] = {"price": 0, "chg_pct": 0}
        if "ccl" in html.lower():
            result["ccl"] = {"price": 0, "chg_pct": 0}
        
        return jsonify(result)
    except Exception as e:
        logger.error(f"Error fetching exchange rates: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/status")
def status():
    """Retorna el estado actual del scanner."""
    return jsonify({
        "running":        scanner_state["running"],
        "session":        scanner_state["session"],
        "progress":       scanner_state["progress"],
        "total":          scanner_state["total"],
        "current_ticker": scanner_state["current_ticker"],
        "results":        scanner_state["results"],
        "log":            scanner_state["log"][-30:],
        "last_run":       scanner_state["last_run"],
    })


@app.route("/historial")
def historial():
    """Retorna el historial completo del Excel."""
    return jsonify(get_historial())


@app.route("/yahoo")
def yahoo_quotes():
    """Retorna precios y variación de una lista de símbolos."""
    symbols = request.args.get("symbols", "").split(",")
    result  = {}
    try:
        data = yf.download(symbols, period="6mo", interval="1d",
                           auto_adjust=True, progress=False, threads=True)
        closes = data["Close"] if "Close" in data else data
        
        for sym in symbols:
            sym = sym.strip()
            try:
                col  = closes[sym] if sym in closes.columns else closes.iloc[:, 0]
                vals = col.dropna()
                if len(vals) >= 2:
                    prev  = float(vals.iloc[-2])
                    last  = float(vals.iloc[-1])
                    result[sym] = {
                        "price":   round(last, 2),
                        "chg_pct": round((last - prev) / prev * 100, 2),
                    }
                elif len(vals) == 1:
                    result[sym] = {"price": round(float(vals.iloc[-1]), 2), "chg_pct": 0}
            except Exception:
                pass
    except Exception as e:
        logger.error(f"Error fetching yahoo quotes: {e}")
    
    return jsonify(result)


@app.route("/sector_data")
def sector_data():
    """Retorna historial de 6 meses + precio actual."""
    tickers = request.args.get("tickers", "").split(",")
    tickers = [t.strip() for t in tickers if t.strip()]
    result  = {}

    try:
        def fetch_yf(sym):
            try:
                t = yf.Ticker(sym)
                df = t.history(period="6mo", interval="1d", auto_adjust=True)
                if df.empty:
                    return None
                df.columns = [c.lower() for c in df.columns]
                df = df.reset_index()
                df["date"] = pd.to_datetime(df["Date"] if "Date" in df.columns else df.index)
                return df[["date","close"]].dropna()
            except Exception:
                return None

        for t in tickers:
            try:
                df = fetch_yf(t)
                if df is None or len(df) < 5:
                    continue

                hist  = [{"date": str(r["date"].date()), "close": round(float(r["close"]), 2)}
                         for _, r in df.iterrows()]
                last  = float(df["close"].iloc[-1])
                prev  = float(df["close"].iloc[-2]) if len(df) >= 2 else last
                result[t] = {
                    "price":   round(last, 2),
                    "chg_pct": round((last - prev) / prev * 100, 2),
                    "history": hist,
                }
            except Exception:
                pass

    except Exception as e:
        logger.error(f"Error fetching sector data: {e}")

    return jsonify(result)


@app.route("/watchlist_data")
def watchlist_data():
    """Retorna RSI, MACD, ATR y precio actual para una lista de tickers."""
    tickers = request.args.get("tickers", "").split(",")
    tickers = [t.strip() for t in tickers if t.strip()]
    if not tickers:
        return jsonify({})
    result = {}
    try:
        data = yf.download(tickers, period="3mo", interval="1d",
                           auto_adjust=True, progress=False, threads=True)

        closes = data["Close"]  if "Close"  in data else data
        highs  = data["High"]   if "High"   in data else None
        lows   = data["Low"]    if "Low"    in data else None

        for t in tickers:
            try:
                c = closes[t].dropna() if t in closes.columns else closes.iloc[:,0].dropna()
                if len(c) < 26:
                    continue

                price   = round(float(c.iloc[-1]), 2)
                prev    = float(c.iloc[-2])
                chg_pct = round((price - prev) / prev * 100, 2)

                result[t] = {
                    "price":    price,
                    "chg_pct":  chg_pct,
                    "sparkline": [round(float(v),2) for v in c.iloc[-20:].tolist()],
                }
            except Exception:
                pass
    except Exception as e:
        logger.error(f"Error fetching watchlist data: {e}")

    return jsonify(result)


if __name__ == "__main__":
    try:
        scheduler.start()
    except Exception as e:
        logger.warning(f"Scheduler already running: {e}")
    
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
