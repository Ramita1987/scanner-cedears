"""
╔══════════════════════════════════════════════════════════════╗
║         SCANNER CEDEARS — INTERFAZ WEB                      ║
║         Flask App para Render.com                           ║
╚══════════════════════════════════════════════════════════════╝
"""

from flask import Flask, render_template, jsonify, request
import threading
import json
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

app = Flask(__name__)

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
                    "rsi":          row[8],
                    "vol_rel":      row[9],
                    "atr":          row[10],
                    "descripcion":  row[11],
                })
        return list(reversed(rows))  # más recientes primero
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
    active_setups = body.get("active_setups", None)  # None = todos

    t = threading.Thread(
        target=run_scanner_thread,
        args=(session, params, active_setups),
        daemon=True
    )
    t.start()
    return jsonify({"ok": True, "session": session})


@app.route("/news")
def news():
    """Retorna las últimas noticias financieras via RSS."""
    import xml.etree.ElementTree as ET
    feeds = [
        ("Reuters", "https://feeds.reuters.com/reuters/businessNews"),
        ("MarketWatch", "https://feeds.content.dowjones.io/public/rss/mw_realtimeheadlines"),
        ("Yahoo Finance", "https://finance.yahoo.com/news/rssindex"),
    ]
    items = []
    for source, url in feeds:
        try:
            r = requests.get(url, timeout=8, headers={"User-Agent": "Mozilla/5.0"})
            root = ET.fromstring(r.content)
            for item in root.iter("item"):
                title = item.findtext("title", "").strip()
                link  = item.findtext("link", "").strip()
                pub   = item.findtext("pubDate", "").strip()
                if title:
                    items.append({"source": source, "title": title, "url": link, "time": pub[:16] if pub else ""})
                if len(items) >= 10:
                    break
        except Exception:
            pass
        if len(items) >= 10:
            break
    return jsonify(items[:5])


@app.route("/status")
def status():
    """Retorna el estado actual del scanner (polling desde el frontend)."""
    return jsonify({
        "running":        scanner_state["running"],
        "session":        scanner_state["session"],
        "progress":       scanner_state["progress"],
        "total":          scanner_state["total"],
        "current_ticker": scanner_state["current_ticker"],
        "results":        scanner_state["results"],
        "log":            scanner_state["log"][-30:],  # últimas 30 líneas
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
        import yfinance as yf
        data = yf.download(symbols, period="2d", interval="1d",
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
        return jsonify({"error": str(e)}), 500
    return jsonify(result)


@app.route("/sector_data")
def sector_data():
    """Retorna historial de 30 días + precio actual para un grupo de tickers."""
    tickers = request.args.get("tickers", "").split(",")
    tickers = [t.strip() for t in tickers if t.strip()]
    result  = {}
    try:
        import yfinance as yf
        import pandas as pd
        data = yf.download(tickers, period="35d", interval="1d",
                           auto_adjust=True, progress=False, threads=True)
        closes = data["Close"] if "Close" in data else data

        for t in tickers:
            try:
                col  = closes[t] if t in closes.columns else closes.iloc[:, 0]
                vals = col.dropna()
                hist = [{"date": str(idx.date()), "close": round(float(v), 2)}
                        for idx, v in vals.items()]
                prev = float(vals.iloc[-2]) if len(vals) >= 2 else float(vals.iloc[-1])
                last = float(vals.iloc[-1])
                result[t] = {
                    "price":   round(last, 2),
                    "chg_pct": round((last - prev) / prev * 100, 2),
                    "history": hist,
                }
            except Exception:
                pass
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    return jsonify(result)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
