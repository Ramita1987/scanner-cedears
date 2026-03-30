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
import requests
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
    """Retorna las últimas noticias financieras en español via RSS."""
    import xml.etree.ElementTree as ET
    feeds = [
        ("El Cronista",    "https://www.cronista.com/files/rss/mercados.xml"),
        ("Infobae",        "https://www.infobae.com/feeds/rss/economia/"),
        ("Ámbito",         "https://www.ambito.com/rss/pages/economia.html"),
        ("Reuters ES",     "https://feeds.reuters.com/reuters/MXeconomicsNews"),
        ("Bloomberg ES",   "https://feeds.bloomberg.com/markets/news.rss"),
    ]
    items = []
    for source, url in feeds:
        try:
            r = requests.get(url, timeout=6, headers={
                "User-Agent": "Mozilla/5.0 (compatible; RSSReader/1.0)"
            })
            root = ET.fromstring(r.content)
            for item in root.iter("item"):
                title = item.findtext("title", "").strip()
                link  = item.findtext("link", "").strip()
                pub   = item.findtext("pubDate", "").strip()
                if title and len(title) > 15:
                    items.append({
                        "source": source,
                        "title":  title,
                        "url":    link,
                        "time":   pub[:16] if pub else ""
                    })
                if len(items) >= 8:
                    break
        except Exception:
            pass
        if len(items) >= 8:
            break

    # Fallback si ningún feed respondió
    if not items:
        items = [
            {"source": "Info", "title": "No se pudieron cargar las noticias en este momento.", "url": "#", "time": ""},
        ]

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
    """Retorna precios y variación. Fetch individual para mayor confiabilidad."""
    symbols = [s.strip() for s in request.args.get("symbols", "").split(",") if s.strip()]
    result  = {}
    try:
        import yfinance as yf
        # Fetch individually — more reliable than batch on servers
        for sym in symbols:
            try:
                t    = yf.Ticker(sym)
                hist = t.history(period="5d", interval="1d", auto_adjust=True)
                if hist.empty:
                    continue
                hist.columns = [c.lower() for c in hist.columns]
                closes = hist["close"].dropna()
                if len(closes) >= 2:
                    last = float(closes.iloc[-1])
                    prev = float(closes.iloc[-2])
                    result[sym] = {
                        "price":   round(last, 2),
                        "chg_pct": round((last - prev) / prev * 100, 2),
                    }
                elif len(closes) == 1:
                    result[sym] = {"price": round(float(closes.iloc[-1]), 2), "chg_pct": 0.0}
            except Exception:
                pass
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    return jsonify(result)


@app.route("/sector_data")
def sector_data():
    """Retorna historial de 30 días + precio actual. Usa Stooq como fuente confiable."""
    tickers = request.args.get("tickers", "").split(",")
    tickers = [t.strip() for t in tickers if t.strip()]
    result  = {}

    try:
        import yfinance as yf
        import pandas as pd

        # Intentar con Stooq primero (más confiable en servidores)
        def fetch_stooq(sym):
            try:
                url = f"https://stooq.com/q/d/l/?s={sym.lower()}&i=d"
                df  = pd.read_csv(url)
                df.columns = [c.lower() for c in df.columns]
                df["date"] = pd.to_datetime(df["date"])
                df = df.sort_values("date").tail(130)  # ~6 meses
                return df[["date","close"]].dropna()
            except Exception:
                return None

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
                df = fetch_stooq(t)
                if df is None or len(df) < 5:
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
        return jsonify({"error": str(e)}), 500

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
        import yfinance as yf
        import numpy as np
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

                # Precio y variación
                price   = round(float(c.iloc[-1]), 2)
                prev    = float(c.iloc[-2])
                chg_pct = round((price - prev) / prev * 100, 2)

                # RSI 14
                delta = c.diff()
                gain  = delta.clip(lower=0).rolling(14).mean()
                loss  = (-delta.clip(upper=0)).rolling(14).mean()
                rs    = gain / loss.replace(0, float('nan'))
                rsi   = round(float(100 - (100 / (1 + rs.iloc[-1]))), 1)

                # MACD (12, 26, 9)
                ema12 = c.ewm(span=12, adjust=False).mean()
                ema26 = c.ewm(span=26, adjust=False).mean()
                macd_line   = ema12 - ema26
                signal_line = macd_line.ewm(span=9, adjust=False).mean()
                macd_val    = round(float(macd_line.iloc[-1]), 3)
                signal_val  = round(float(signal_line.iloc[-1]), 3)
                macd_hist   = round(macd_val - signal_val, 3)

                # ATR 14
                atr_val = None
                if highs is not None and lows is not None:
                    h = highs[t].dropna() if t in highs.columns else None
                    l = lows[t].dropna()  if t in lows.columns  else None
                    if h is not None and l is not None and len(h) > 14:
                        import pandas as pd
                        tr = pd.concat([h-l,(h-c.shift()).abs(),(l-c.shift()).abs()],axis=1).max(axis=1)
                        atr_val = round(float(tr.rolling(14).mean().iloc[-1]), 2)

                # Señal MACD
                macd_signal_str = "COMPRA" if macd_val > signal_val else "VENTA" if macd_val < signal_val else "NEUTRO"

                result[t] = {
                    "price":    price,
                    "chg_pct":  chg_pct,
                    "rsi":      rsi,
                    "macd":     macd_val,
                    "macd_signal": signal_val,
                    "macd_hist":   macd_hist,
                    "macd_str":    macd_signal_str,
                    "atr":      atr_val,
                    # Mini histórico para sparkline (últimos 20 cierres)
                    "sparkline": [round(float(v),2) for v in c.iloc[-20:].tolist()],
                }
            except Exception:
                pass
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    return jsonify(result)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
