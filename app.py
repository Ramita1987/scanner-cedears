"""
╔══════════════════════════════════════════════════════════════╗
║         SCANNER CEDEARS — INTERFAZ WEB                      ║
║         Flask App para Render.com                           ║
╚══════════════════════════════════════════════════════════════╝
"""

from flask import Flask, render_template, jsonify, request
import threading
import os
import sys
import requests
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

app = Flask(__name__)

# ── Alpha Vantage API Key ────────────────────────────────────────
AV_KEY = os.environ.get("AV_KEY", "6IFZV2E8RQ6BMJ0L")

# ── Estado global del scanner ────────────────────────────────────
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


# ═══════════════════════════════════════════════════════════════
#  SCANNER THREAD
# ═══════════════════════════════════════════════════════════════

def run_scanner_thread(session: str, params: dict = None, active_setups: list = None):
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
            except Exception:
                scanner_state["log"].append(f"⚠️ {ticker} — error")

            import time
            time.sleep(0.3) if i % 10 != 0 else time.sleep(2)

        resultados.sort(key=lambda x: (x["probabilidad"], x["confluencias"], x["vol_rel"]), reverse=True)
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


# ═══════════════════════════════════════════════════════════════
#  HISTORIAL
# ═══════════════════════════════════════════════════════════════

def get_historial():
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
                    "fecha": row[0], "hora": row[1], "sesion": row[2],
                    "ticker": row[3], "setup": row[4], "confluencias": row[5],
                    "probabilidad": row[6], "precio": row[7],
                    "target": row[8], "stop": row[9],
                    "rsi": row[10], "vol_rel": row[11], "atr": row[12],
                    "descripcion": row[13],
                    "resultado": row[14] if len(row) > 14 else "Pendiente",
                })
        return list(reversed(rows))
    except Exception:
        return []


# ═══════════════════════════════════════════════════════════════
#  ALPHA VANTAGE — COTIZACIONES
# ═══════════════════════════════════════════════════════════════

def av_quote(symbol: str) -> dict:
    """Obtiene precio actual y variación via Alpha Vantage."""
    try:
        url = (f"https://www.alphavantage.co/query"
               f"?function=GLOBAL_QUOTE&symbol={symbol}&apikey={AV_KEY}")
        r = requests.get(url, timeout=10)
        d = r.json().get("Global Quote", {})
        if not d or "05. price" not in d:
            return {}
        price   = float(d["05. price"])
        chg_pct = float(d["10. change percent"].replace("%",""))
        return {"price": round(price, 2), "chg_pct": round(chg_pct, 2)}
    except Exception:
        return {}


def av_daily(symbol: str, months: int = 6) -> list:
    """Obtiene historial diario via Alpha Vantage (últimos N meses)."""
    try:
        url = (f"https://www.alphavantage.co/query"
               f"?function=TIME_SERIES_DAILY&symbol={symbol}"
               f"&outputsize=compact&apikey={AV_KEY}")
        r    = requests.get(url, timeout=15)
        data = r.json().get("Time Series (Daily)", {})
        if not data:
            return []
        items = sorted(data.items())  # oldest first
        # compact = 100 días (~5 meses), suficiente
        hist = [{"date": d, "close": round(float(v["4. close"]), 2)}
                for d, v in items]
        return hist[-130:]  # ~6 meses
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
    session = session.upper()
    if session not in ["PRE-MARKET", "APERTURA", "CIERRE", "MANUAL"]:
        return jsonify({"error": "Sesión inválida"}), 400
    if scanner_state["running"]:
        return jsonify({"error": "El scanner ya está corriendo"}), 400
    body          = request.get_json(silent=True) or {}
    params        = body.get("params", {})
    active_setups = body.get("active_setups", None)
    t = threading.Thread(target=run_scanner_thread, args=(session, params, active_setups), daemon=True)
    t.start()
    return jsonify({"ok": True, "session": session})


@app.route("/status")
def status():
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
    return jsonify(get_historial())


@app.route("/yahoo")
def yahoo_quotes():
    """
    Cotizaciones usando Alpha Vantage.
    El frontend sigue llamando /yahoo para no cambiar el JS.
    Nota: AV free = 25 req/día → cacheamos en memoria por 10 min.
    """
    symbols = [s.strip() for s in request.args.get("symbols","").split(",") if s.strip()]
    result  = {}

    # Cache simple en memoria
    now = datetime.now()
    if not hasattr(app, '_quote_cache'):
        app._quote_cache = {}

    for sym in symbols:
        # Verificar cache (válido por 10 minutos)
        cached = app._quote_cache.get(sym)
        if cached and (now - cached["ts"]).seconds < 600:
            result[sym] = cached["data"]
            continue

        # Para índices y futuros que AV no soporta, usar yfinance
        if sym.startswith("^") or sym.endswith("=F") or "-" in sym:
            try:
                import yfinance as yf
                t    = yf.Ticker(sym)
                hist = t.history(period="5d", interval="1d", auto_adjust=True)
                if not hist.empty:
                    closes = hist["Close"].dropna()
                    if len(closes) >= 2:
                        last = float(closes.iloc[-1])
                        prev = float(closes.iloc[-2])
                        d = {"price": round(last,2), "chg_pct": round((last-prev)/prev*100,2)}
                        result[sym] = d
                        app._quote_cache[sym] = {"data": d, "ts": now}
            except Exception:
                pass
            continue

        # Alpha Vantage para acciones normales
        d = av_quote(sym)
        if d:
            result[sym] = d
            app._quote_cache[sym] = {"data": d, "ts": now}

        import time
        time.sleep(0.5)  # respetar rate limit AV

    return jsonify(result)


@app.route("/sector_data")
def sector_data():
    """Historial de 6 meses via Alpha Vantage."""
    tickers = [t.strip() for t in request.args.get("tickers","").split(",") if t.strip()]
    result  = {}

    # Cache por 30 minutos (los gráficos no necesitan actualizarse seguido)
    now = datetime.now()
    if not hasattr(app, '_sector_cache'):
        app._sector_cache = {}

    for sym in tickers:
        cached = app._sector_cache.get(sym)
        if cached and (now - cached["ts"]).seconds < 1800:
            result[sym] = cached["data"]
            continue

        hist = av_daily(sym)
        if len(hist) < 5:
            # Fallback yfinance
            try:
                import yfinance as yf
                import pandas as pd
                t  = yf.Ticker(sym)
                df = t.history(period="6mo", interval="1d", auto_adjust=True)
                if not df.empty:
                    df.columns = [c.lower() for c in df.columns]
                    hist = [{"date": str(idx.date()), "close": round(float(row["close"]),2)}
                            for idx, row in df.iterrows()]
            except Exception:
                pass

        if len(hist) < 5:
            continue

        last  = hist[-1]["close"]
        prev  = hist[-2]["close"] if len(hist) >= 2 else last
        d = {
            "price":   last,
            "chg_pct": round((last - prev) / prev * 100, 2),
            "history": hist,
        }
        result[sym] = d
        app._sector_cache[sym] = {"data": d, "ts": now}

        import time
        time.sleep(0.5)

    return jsonify(result)


@app.route("/news")
def news():
    """Noticias financieras en español via RSS."""
    import xml.etree.ElementTree as ET
    feeds = [
        ("El Cronista",  "https://www.cronista.com/files/rss/mercados.xml"),
        ("Ámbito",       "https://www.ambito.com/rss/pages/economia.html"),
        ("Infobae",      "https://www.infobae.com/feeds/rss/economia/"),
        ("iProfesional", "https://www.iprofesional.com/rss/home.xml"),
        ("Reuters ES",   "https://feeds.reuters.com/reuters/MXeconomicsNews"),
    ]
    items = []
    for source, url in feeds:
        try:
            r = requests.get(url, timeout=6, headers={"User-Agent": "Mozilla/5.0"})
            root = ET.fromstring(r.content)
            for item in root.iter("item"):
                title = item.findtext("title","").strip()
                link  = item.findtext("link","").strip()
                pub   = item.findtext("pubDate","").strip()
                if title and len(title) > 15:
                    items.append({"source": source, "title": title, "url": link, "time": pub[:16] if pub else ""})
                if len(items) >= 8:
                    break
        except Exception:
            pass
        if len(items) >= 8:
            break

    if not items:
        items = [{"source": "Info", "title": "No se pudieron cargar las noticias.", "url": "#", "time": ""}]

    return jsonify(items[:5])


@app.route("/watchlist_data")
def watchlist_data():
    """RSI, MACD, ATR via Alpha Vantage + cálculo local."""
    tickers = [t.strip() for t in request.args.get("tickers","").split(",") if t.strip()]
    if not tickers:
        return jsonify({})
    result = {}
    import time

    for sym in tickers:
        try:
            hist = av_daily(sym, months=3)
            if len(hist) < 26:
                continue

            import pandas as pd
            import numpy as np
            closes = pd.Series([h["close"] for h in hist])

            last    = float(closes.iloc[-1])
            prev    = float(closes.iloc[-2])
            chg_pct = round((last - prev) / prev * 100, 2)

            # RSI 14
            delta = closes.diff()
            gain  = delta.clip(lower=0).rolling(14).mean()
            loss  = (-delta.clip(upper=0)).rolling(14).mean()
            rs    = gain / loss.replace(0, float("nan"))
            rsi   = round(float(100 - (100 / (1 + rs.iloc[-1]))), 1)

            # MACD
            ema12   = closes.ewm(span=12, adjust=False).mean()
            ema26   = closes.ewm(span=26, adjust=False).mean()
            macd    = ema12 - ema26
            signal  = macd.ewm(span=9, adjust=False).mean()
            mv      = round(float(macd.iloc[-1]), 3)
            sv      = round(float(signal.iloc[-1]), 3)
            macd_str = "COMPRA" if mv > sv else "VENTA" if mv < sv else "NEUTRO"

            result[sym] = {
                "price":    round(last, 2),
                "chg_pct":  chg_pct,
                "rsi":      rsi,
                "macd":     mv,
                "macd_signal": sv,
                "macd_hist":   round(mv - sv, 3),
                "macd_str":    macd_str,
                "atr":      None,
                "sparkline": [round(float(v),2) for v in closes.iloc[-20:].tolist()],
            }
        except Exception:
            pass
        time.sleep(0.5)

    return jsonify(result)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
