"""
╔══════════════════════════════════════════════════════════════╗
║         SCANNER CEDEARS — INTERFAZ WEB v2                   ║
║         Flask App para Render.com                           ║
╚══════════════════════════════════════════════════════════════╝
"""

from flask import Flask, render_template, jsonify, request
import threading
import os, sys, time
import requests
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

app = Flask(__name__)

# ── API Keys ─────────────────────────────────────────────────────
AV_KEY  = os.environ.get("AV_KEY",  "6IFZV2E8RQ6BMJ0L")   # Alpha Vantage
FMP_KEY = os.environ.get("FMP_KEY", "demo")                 # Financial Modeling Prep (free)

# ── Cache global ─────────────────────────────────────────────────
_cache = {}

def get_cache(key, ttl=600):
    """Retorna valor cacheado si no expiró (ttl en segundos)."""
    if key in _cache:
        val, ts = _cache[key]
        if (datetime.now() - ts).seconds < ttl:
            return val
    return None

def set_cache(key, val):
    _cache[key] = (val, datetime.now())
    return val

# ── Estado scanner ────────────────────────────────────────────────
scanner_state = {
    "running": False, "session": "", "progress": 0, "total": 0,
    "current_ticker": "", "results": [], "log": [], "last_run": None,
}


# ═══════════════════════════════════════════════════════════════
#  FUENTES DE DATOS — Sin Yahoo Finance
# ═══════════════════════════════════════════════════════════════

def fmp_quote(symbols: list) -> dict:
    """
    Financial Modeling Prep — cotizaciones en tiempo real.
    Plan free: funciona con 'demo' para tickers populares.
    Endpoint: https://financialmodelingprep.com/api/v3/quote/AAPL,MSFT
    """
    result = {}
    if not symbols:
        return result
    try:
        syms_str = ",".join(symbols)
        url = f"https://financialmodelingprep.com/api/v3/quote/{syms_str}?apikey={FMP_KEY}"
        r   = requests.get(url, timeout=10, headers={"User-Agent": "Mozilla/5.0"})
        if r.status_code != 200:
            return result
        data = r.json()
        if not isinstance(data, list):
            return result
        for item in data:
            sym = item.get("symbol","")
            if sym:
                result[sym] = {
                    "price":   round(float(item.get("price", 0)), 2),
                    "chg_pct": round(float(item.get("changesPercentage", 0)), 2),
                }
    except Exception:
        pass
    return result


def fmp_index_quote(symbol_map: dict) -> dict:
    """
    Cotizaciones de índices via FMP.
    symbol_map: {display_name: fmp_symbol}
    e.g. {"S&P 500": "^GSPC", "NASDAQ": "^IXIC"}
    """
    result = {}
    try:
        syms = list(symbol_map.values())
        data = fmp_quote(syms)
        for name, sym in symbol_map.items():
            if sym in data:
                result[name] = data[sym]
    except Exception:
        pass
    return result


def av_quote_single(symbol: str) -> dict:
    """Alpha Vantage — cotización individual."""
    cached = get_cache(f"av_{symbol}", ttl=600)
    if cached:
        return cached
    try:
        url = (f"https://www.alphavantage.co/query"
               f"?function=GLOBAL_QUOTE&symbol={symbol}&apikey={AV_KEY}")
        r = requests.get(url, timeout=10)
        d = r.json().get("Global Quote", {})
        if not d or "05. price" not in d:
            return {}
        val = {
            "price":   round(float(d["05. price"]), 2),
            "chg_pct": round(float(d["10. change percent"].replace("%","")), 2),
        }
        return set_cache(f"av_{symbol}", val)
    except Exception:
        return {}


def av_daily(symbol: str) -> list:
    """Alpha Vantage — historial diario (~5 meses compact)."""
    cached = get_cache(f"avd_{symbol}", ttl=3600)
    if cached:
        return cached
    try:
        url = (f"https://www.alphavantage.co/query"
               f"?function=TIME_SERIES_DAILY&symbol={symbol}"
               f"&outputsize=compact&apikey={AV_KEY}")
        r    = requests.get(url, timeout=15)
        data = r.json().get("Time Series (Daily)", {})
        if not data:
            return []
        hist = [{"date": d, "close": round(float(v["4. close"]), 2)}
                for d, v in sorted(data.items())]
        return set_cache(f"avd_{symbol}", hist[-130:])
    except Exception:
        return []


def dolarapi() -> dict:
    """Cotizaciones del dólar en Argentina."""
    cached = get_cache("dolar", ttl=300)
    if cached:
        return cached
    try:
        r    = requests.get("https://dolarapi.com/v1/dolares", timeout=8)
        data = r.json()
        tipos = {"oficial":"Oficial","blue":"Blue","contadoconliqui":"CCL","bolsa":"MEP"}
        result = {}
        for item in data:
            if item["casa"] in tipos:
                result[tipos[item["casa"]]] = {
                    "compra": item.get("compra", 0),
                    "venta":  item.get("venta", 0),
                }
        return set_cache("dolar", result)
    except Exception:
        return {}


# ═══════════════════════════════════════════════════════════════
#  SCANNER THREAD
# ═══════════════════════════════════════════════════════════════

def run_scanner_thread(session: str, params: dict = None, active_setups: list = None):
    global scanner_state
    scanner_state.update({"running":True,"session":session,"progress":0,
                          "results":[],"log":[],"current_ticker":""})
    try:
        import importlib, scanner as sc
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
                    scanner_state["log"].append(f"✅ {ticker.replace('.BA','')} — {res['setup']} | {res['probabilidad']}%")
                else:
                    scanner_state["log"].append(f"⬜ {ticker.replace('.BA','')} — sin setup")
            except Exception:
                scanner_state["log"].append(f"⚠️ {ticker} — error")
            time.sleep(0.3) if i % 10 != 0 else time.sleep(2)
        resultados.sort(key=lambda x:(x["probabilidad"],x["confluencias"],x["vol_rel"]),reverse=True)
        top = resultados[:tn]
        scanner_state["results"]  = top
        scanner_state["last_run"] = datetime.now().strftime("%d/%m/%Y %H:%M")
        if top:
            sc.guardar_excel(top, session)
        sc.send_telegram(sc.build_telegram_message(top, session))
        scanner_state["log"].append(f"\n🏁 Completado. {len(top)} oportunidades.")
    except Exception as e:
        scanner_state["log"].append(f"❌ Error: {e}")
    finally:
        scanner_state["running"] = False


# ═══════════════════════════════════════════════════════════════
#  HISTORIAL
# ═══════════════════════════════════════════════════════════════

def get_historial():
    try:
        from openpyxl import load_workbook
        archivo = os.path.join(os.path.dirname(os.path.abspath(__file__)), "registros_scanner.xlsx")
        if not os.path.exists(archivo): return []
        wb = load_workbook(archivo); ws = wb.active
        rows = []
        for row in ws.iter_rows(min_row=2, values_only=True):
            if row[0]:
                rows.append({
                    "fecha":row[0],"hora":row[1],"sesion":row[2],"ticker":row[3],
                    "setup":row[4],"confluencias":row[5],"probabilidad":row[6],
                    "precio":row[7],"target":row[8],"stop":row[9],
                    "rsi":row[10],"vol_rel":row[11],"atr":row[12],
                    "descripcion":row[13],
                    "resultado":row[14] if len(row)>14 else "Pendiente",
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
    session = session.upper()
    if session not in ["PRE-MARKET","APERTURA","CIERRE","MANUAL"]:
        return jsonify({"error":"Sesión inválida"}),400
    if scanner_state["running"]:
        return jsonify({"error":"El scanner ya está corriendo"}),400
    body = request.get_json(silent=True) or {}
    t = threading.Thread(target=run_scanner_thread,
        args=(session, body.get("params",{}), body.get("active_setups",None)), daemon=True)
    t.start()
    return jsonify({"ok":True,"session":session})


@app.route("/status")
def status():
    return jsonify({k: scanner_state[k] for k in
        ["running","session","progress","total","current_ticker","results","last_run",
         "log"]})


@app.route("/historial")
def historial():
    return jsonify(get_historial())


@app.route("/market")
def market():
    """
    Endpoint unificado de datos de mercado.
    Retorna: indices, commodities, crypto, movers, dolar
    Usa FMP (indices/acciones) + dolarapi (dolar)
    """
    cached = get_cache("market", ttl=300)
    if cached:
        return jsonify(cached)

    # ── Índices via FMP ──────────────────────────────────────
    idx_syms = ["^GSPC","^IXIC","^DJI","^RUT","^VIX","MERVAL"]
    idx_data = fmp_quote(idx_syms)

    indices = [
        {"n":"S&P 500",      "s":"^GSPC",  "d": idx_data.get("^GSPC",{})},
        {"n":"NASDAQ",       "s":"^IXIC",  "d": idx_data.get("^IXIC",{})},
        {"n":"Dow Jones",    "s":"^DJI",   "d": idx_data.get("^DJI",{})},
        {"n":"Russell 2000", "s":"^RUT",   "d": idx_data.get("^RUT",{})},
        {"n":"VIX",          "s":"^VIX",   "d": idx_data.get("^VIX",{})},
        {"n":"Merval",       "s":"MERVAL", "d": idx_data.get("MERVAL",{})},
    ]

    # ── Commodities via FMP ──────────────────────────────────
    com_syms  = ["GCUSD","CLUSD","SIUSD","HGUSD"]
    com_data  = fmp_quote(com_syms)
    commodities = [
        {"n":"Oro",          "d": com_data.get("GCUSD",{})},
        {"n":"Petróleo WTI", "d": com_data.get("CLUSD",{})},
        {"n":"Plata",        "d": com_data.get("SIUSD",{})},
        {"n":"Cobre",        "d": com_data.get("HGUSD",{})},
    ]

    # ── Crypto via FMP ───────────────────────────────────────
    cry_syms = ["BTCUSD","ETHUSD"]
    cry_data = fmp_quote(cry_syms)
    crypto = [
        {"n":"Bitcoin (BTC)",  "d": cry_data.get("BTCUSD",{})},
        {"n":"Ethereum (ETH)", "d": cry_data.get("ETHUSD",{})},
    ]

    # ── Movers via FMP ───────────────────────────────────────
    wl_syms = ["AAPL","MSFT","GOOGL","AMZN","NVDA","META","TSLA",
               "JPM","BAC","V","MA","XOM","CVX","JNJ","UNH",
               "GGAL","YPF","MELI","NU","BABA"]
    wl_data = fmp_quote(wl_syms)
    movers  = [{"s":s,"price":wl_data[s]["price"],"chg_pct":wl_data[s]["chg_pct"]}
               for s in wl_syms if s in wl_data and wl_data[s].get("chg_pct") is not None]
    movers.sort(key=lambda x: x["chg_pct"], reverse=True)

    # ── Dólar ────────────────────────────────────────────────
    dolar = dolarapi()

    result = {
        "indices":     indices,
        "commodities": commodities,
        "crypto":      crypto,
        "gainers":     movers[:5],
        "losers":      movers[-5:][::-1],
        "dolar":       dolar,
    }
    set_cache("market", result)
    return jsonify(result)


@app.route("/sector_data")
def sector_data():
    """Historial 6 meses via Alpha Vantage."""
    tickers = [t.strip() for t in request.args.get("tickers","").split(",") if t.strip()]
    result  = {}
    for sym in tickers:
        cached = get_cache(f"sec_{sym}", ttl=3600)
        if cached:
            result[sym] = cached
            continue
        hist = av_daily(sym)
        if len(hist) < 5:
            continue
        last = hist[-1]["close"]
        prev = hist[-2]["close"] if len(hist)>=2 else last
        d = {"price":last,"chg_pct":round((last-prev)/prev*100,2),"history":hist}
        result[sym] = set_cache(f"sec_{sym}", d)
        time.sleep(0.3)
    return jsonify(result)


@app.route("/watchlist_data")
def watchlist_data():
    """RSI, MACD via Alpha Vantage."""
    tickers = [t.strip() for t in request.args.get("tickers","").split(",") if t.strip()]
    if not tickers: return jsonify({})
    result = {}
    import pandas as pd
    for sym in tickers:
        try:
            hist = av_daily(sym)
            if len(hist) < 26: continue
            closes = pd.Series([h["close"] for h in hist])
            last    = float(closes.iloc[-1])
            prev    = float(closes.iloc[-2])
            chg_pct = round((last-prev)/prev*100,2)
            delta = closes.diff()
            gain  = delta.clip(lower=0).rolling(14).mean()
            loss  = (-delta.clip(upper=0)).rolling(14).mean()
            rs    = gain/loss.replace(0,float("nan"))
            rsi   = round(float(100-(100/(1+rs.iloc[-1]))),1)
            ema12 = closes.ewm(span=12,adjust=False).mean()
            ema26 = closes.ewm(span=26,adjust=False).mean()
            macd  = ema12-ema26
            sig   = macd.ewm(span=9,adjust=False).mean()
            mv,sv = round(float(macd.iloc[-1]),3),round(float(sig.iloc[-1]),3)
            result[sym] = {
                "price":last,"chg_pct":chg_pct,"rsi":rsi,
                "macd":mv,"macd_signal":sv,"macd_hist":round(mv-sv,3),
                "macd_str":"COMPRA" if mv>sv else "VENTA" if mv<sv else "NEUTRO",
                "atr":None,
                "sparkline":[round(float(v),2) for v in closes.iloc[-20:].tolist()],
            }
        except Exception:
            pass
        time.sleep(0.3)
    return jsonify(result)


@app.route("/news")
def news():
    """Noticias en español via RSS."""
    import xml.etree.ElementTree as ET
    cached = get_cache("news", ttl=300)
    if cached: return jsonify(cached)
    feeds = [
        ("El Cronista",  "https://www.cronista.com/files/rss/mercados.xml"),
        ("Ámbito",       "https://www.ambito.com/rss/pages/economia.html"),
        ("Infobae",      "https://www.infobae.com/feeds/rss/economia/"),
        ("iProfesional", "https://www.iprofesional.com/rss/home.xml"),
    ]
    items = []
    for source, url in feeds:
        try:
            r    = requests.get(url, timeout=6, headers={"User-Agent":"Mozilla/5.0"})
            root = ET.fromstring(r.content)
            for item in root.iter("item"):
                title = item.findtext("title","").strip()
                link  = item.findtext("link","").strip()
                pub   = item.findtext("pubDate","").strip()
                if title and len(title)>15:
                    items.append({"source":source,"title":title,"url":link,"time":pub[:16] if pub else ""})
                if len(items)>=8: break
        except Exception:
            pass
        if len(items)>=8: break
    if not items:
        items=[{"source":"Info","title":"No se pudieron cargar las noticias.","url":"#","time":""}]
    result = items[:5]
    set_cache("news", result)
    return jsonify(result)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
