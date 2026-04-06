"""
╔══════════════════════════════════════════════════════════════╗
║              CONFIGURACIÓN DEL SCANNER                      ║
║   Editá este archivo con tus credenciales y preferencias    ║
╚══════════════════════════════════════════════════════════════╝
"""

# ── TELEGRAM ────────────────────────────────────────────────────
# Obtenés el TOKEN hablando con @BotFather en Telegram
# El CHAT_ID lo obtenés enviando un mensaje al bot y consultando:
# https://api.telegram.org/bot<TU_TOKEN>/getUpdates

TELEGRAM_TOKEN   = "8782386140:AAGie0EfONP9qm6XvAQ2mYBFfSmH_9Qhn2A"         # Ej: "7123456789:AAFxxx..."
TELEGRAM_CHAT_ID = "-1003742537108"       # Ej: "123456789"


# ── PARÁMETROS DEL SCANNER ─────────────────────────────────────

TOP_N           = 10     # Cuántas oportunidades mostrar en la alerta
MIN_PROBABILITY = 60.0   # Filtro mínimo de probabilidad (%)


# ── LISTA DE CEDEARS ───────────────────────────────────────────

CEDEARS = [
    # TECNOLOGIA
    "AAPL", "MSFT", "GOOGL", "AMZN", "NVDA",
    "META", "TSLA", "NFLX",  "INTC", "AMD",
    "AVGO", "CRM",  "SHOP",  "PANW", "VRSN",
    "GLOB", "PLTR", "MSI",   "SPOT", "ASML",
    "FSLR", "AMGN", "SAP",

    # ETF TECNOLOGIA
    "XLK", "XLC",

    # SALUD
    "PFE", "JNJ", "UNH", "LLY", "ABBV",

    # ETF SALUD
    "XLV",

    # CONSUMO
    "KO", "WMT", "PEP", "PG", "MCD",

    # ETF CONSUMO
    "XLP", "XLY",

    # MINERIA Y MATERIALES
    "HMY", "GLD", "RIO",

    # ETF MATERIALES
    "XLB",

    # INDUSTRIA
    "DE", "LMT", "CAT", "BA", "GE",

    # ETF INDUSTRIA
    "XLI",

    # FINANZAS
    "JPM", "V", "AXP", "BAC", "MA",
    "BRK-B", "PYPL",

    # ETF FINANZAS
    "XLF",

    # ENERGIA
    "OXY", "XOM", "CVX", "EQNR",

    # ETF ENERGIA
    "XLE",

    # ETF MERCADO
    "DIA", "QQQ", "IWM", "ARKK", "SH",

    # CRYPTO / BITCOIN ETF
    "IBIT", "MSTR",

    # ARGENTINA (ADRs en NYSE)
    "BBAR", "BMA",  "EDN",  "GGAL", "LOMA",
    "PAM",  "SUPV", "TXR",  "VIST", "YPF",

    # BRASIL
    "STNE", "PAGS", "BBD", "NU",   "PBR",
    "XP",   "EWZ",  "MELI",

    # CHINA
    "BABA", "BIDU", "NIO", "JD", "PDD",
    "FXI",

    # ENERGIA NUCLEAR
    "CEG", "NXE", "URA",
]
