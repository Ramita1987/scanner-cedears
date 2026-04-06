"""
Script de ejecucion para GitHub Actions.
Lee credenciales desde variables de entorno y corre el scanner.
"""

import os
import time

# Credenciales y sesion desde environment
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")
SESSION_NAME = os.environ.get("SESSION_NAME", "MANUAL").upper()

if not TELEGRAM_TOKEN:
    print("WARNING: TELEGRAM_TOKEN no configurado; no se enviara mensaje.")

print("=" * 60)
print("  GITHUB ACTIONS - Scanner CEDEARs")
print(f"  Sesion: {SESSION_NAME}")
print(f"  Token configurado: {'SI' if TELEGRAM_TOKEN else 'NO'}")
print("=" * 60 + "\n")

# Cargar config y scanner
import config

config.TELEGRAM_TOKEN = TELEGRAM_TOKEN
config.TELEGRAM_CHAT_ID = TELEGRAM_CHAT_ID

import scanner as sc
from config import CEDEARS, TOP_N, MIN_PROBABILITY

print(f"  Tickers a analizar: {len(CEDEARS)}\n")

resultados = []
errores = 0

for i, ticker in enumerate(CEDEARS, 1):
    print(f"[{i:>3}/{len(CEDEARS)}] {ticker}...", end="  ")
    try:
        res = sc.analizar_ticker(ticker)
        if res and res["probabilidad"] >= MIN_PROBABILITY:
            resultados.append(res)
            print(f"OK {res['setup']} | {res['probabilidad']}%")
        else:
            print("-")
    except Exception as e:
        print(f"ERROR {e}")
        errores += 1

    if i % 10 == 0:
        time.sleep(3)
    else:
        time.sleep(0.5)

# Ranking
resultados.sort(
    key=lambda x: (x["probabilidad"], x["confluencias"], x["vol_rel"]),
    reverse=True
)
top = resultados[:TOP_N]

print(f"\n{'=' * 60}")
print(f"  Completado. Oportunidades: {len(top)} | Errores: {errores}")
print(f"{'=' * 60}\n")

if top:
    print(f"{'#':<3} {'Ticker':<8} {'Setup':<26} {'Conf':>5} {'Prob%':>6} {'Vol':>6} {'RSI':>6}")
    print("-" * 60)
    for i, op in enumerate(top, 1):
        print(
            f"{i:<3} {op['ticker']:<8} {op['setup']:<26} "
            f"{op['confluencias']:>5} {op['probabilidad']:>5.1f}% "
            f"{op['vol_rel']:>5.1f}x {op['rsi']:>5.1f}"
        )
else:
    print("Sin oportunidades con probabilidad > 60%")

msg = sc.build_telegram_message(top, SESSION_NAME)

if TELEGRAM_TOKEN and TELEGRAM_CHAT_ID:
    import requests

    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": msg,
        "parse_mode": "Markdown",
    }
    try:
        r = requests.post(url, json=payload, timeout=15)
        if r.status_code == 200:
            print("\nOK Mensaje enviado a Telegram.")
        else:
            print(f"\nERROR Telegram: {r.status_code} - {r.text[:100]}")
    except Exception as e:
        print(f"\nERROR Excepcion Telegram: {e}")
else:
    print("\nWARNING: Telegram no configurado; mensaje no enviado.")
