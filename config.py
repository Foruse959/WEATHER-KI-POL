"""
Weather Trading Bot — Configuration

Polymarket weather market sniper with multi-source forecasts.
Supports paper (dry-run) and live trading modes.
"""

import os
from dotenv import load_dotenv

load_dotenv()


class Config:
    """Central configuration for weather trading bot."""

    VERSION = "1.0.0"
    VERSION_NAME = "Weather Sniper"

    # ═══════════════════════════════════════════════════════════════════
    # TRADING MODE — paper = dry-run (no real orders), live = real money
    # ═══════════════════════════════════════════════════════════════════
    TRADING_MODE = os.getenv('TRADING_MODE', 'paper')  # 'paper' or 'live'
    STARTING_BALANCE = float(os.getenv('STARTING_BALANCE', '3.0'))

    # ═══════════════════════════════════════════════════════════════════
    # POLYMARKET WALLET (reused from polymarket-bot-v2)
    # ═══════════════════════════════════════════════════════════════════
    POLY_PRIVATE_KEY = os.getenv('POLY_PRIVATE_KEY', '')
    POLY_FUNDER_ADDRESS = os.getenv('POLY_FUNDER_ADDRESS', '')
    POLY_PROXY_WALLET = os.getenv('POLY_PROXY_WALLET', '')
    POLY_API_KEY = os.getenv('POLY_API_KEY', '')
    POLY_API_SECRET = os.getenv('POLY_API_SECRET', '')
    POLY_PASSPHRASE = os.getenv('POLY_PASSPHRASE', '')
    POLY_SIGNATURE_TYPE = int(os.getenv('POLY_SIGNATURE_TYPE', '3'))
    POLY_CHAIN_ID = int(os.getenv('POLY_CHAIN_ID', '137'))
    POLY_BUILDER_CODE = os.getenv('POLY_BUILDER_CODE', '')

    # ═══════════════════════════════════════════════════════════════════
    # API ENDPOINTS
    # ═══════════════════════════════════════════════════════════════════
    GAMMA_API_URL = 'https://gamma-api.polymarket.com'
    CLOB_API_URL = 'https://clob.polymarket.com'
    POLYGON_RPC_URL = os.getenv('POLYGON_RPC_URL', '')

    # ═══════════════════════════════════════════════════════════════════
    # WEATHER API KEYS
    # ═══════════════════════════════════════════════════════════════════
    OPENWEATHER_API_KEY = os.getenv('OPENWEATHER_API_KEY', '')
    # Open-Meteo: no key needed (free, 10k calls/day)
    # weather.gov: no key needed (US gov free)

    # ═══════════════════════════════════════════════════════════════════
    # TRADING PARAMETERS
    # ═══════════════════════════════════════════════════════════════════
    # Sniper strategy: buy buckets priced below this when forecast is strong
    SNIPER_MAX_ENTRY_PRICE = float(os.getenv('SNIPER_MAX_ENTRY_PRICE', '0.15'))
    # Minimum edge (our probability - market price) to enter
    MIN_EDGE_TO_ENTER = float(os.getenv('MIN_EDGE_TO_ENTER', '0.10'))
    # Kelly criterion fraction (conservative)
    KELLY_FRACTION = float(os.getenv('KELLY_FRACTION', '0.15'))
    # Maximum bet as % of balance
    MAX_BET_PCT = float(os.getenv('MAX_BET_PCT', '0.20'))
    # Minimum order size on Polymarket
    MIN_ORDER_SIZE = 1.0
    # Maximum concurrent positions
    MAX_POSITIONS = int(os.getenv('MAX_POSITIONS', '10'))
    # Maximum exposure per single market (% of balance)
    MAX_SINGLE_MARKET_PCT = float(os.getenv('MAX_SINGLE_MARKET_PCT', '0.30'))
    # Stop-loss: close position if ROI drops below this %
    STOP_LOSS_PCT = float(os.getenv('STOP_LOSS_PCT', '-80'))
    # Trailing stop: sell if price drops X% from peak (only after 2x gain)
    TRAILING_STOP_PCT = float(os.getenv('TRAILING_STOP_PCT', '25'))

    # ═══════════════════════════════════════════════════════════════════
    # MULTI-OUTCOME SPREAD STRATEGY
    # ═══════════════════════════════════════════════════════════════════
    SPREAD_ENABLED = os.getenv('SPREAD_STRATEGY_ENABLED', '1') == '1'
    # Buy primary bucket + neighbors with decaying size
    SPREAD_NEIGHBOR_DECAY = float(os.getenv('SPREAD_NEIGHBOR_DECAY', '0.4'))
    # Max total cost for a spread position
    SPREAD_MAX_COST = float(os.getenv('SPREAD_MAX_COST', '1.50'))

    # ═══════════════════════════════════════════════════════════════════
    # SCAN SETTINGS
    # ═══════════════════════════════════════════════════════════════════
    SCAN_INTERVAL_SECONDS = int(os.getenv('SCAN_INTERVAL_SECONDS', '60'))
    SCAN_DAYS_AHEAD = int(os.getenv('SCAN_DAYS_AHEAD', '3'))

    # ═══════════════════════════════════════════════════════════════════
    # TELEGRAM (optional notifications)
    # ═══════════════════════════════════════════════════════════════════
    TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN', '')
    TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID', '')

    # ═══════════════════════════════════════════════════════════════════
    # ML DECISION ENGINE (GPT-5.5 via Freemodel)
    # ═══════════════════════════════════════════════════════════════════
    ML_API_URL = os.getenv('ML_API_URL', 'https://vip-sg.freemodel.dev/v1')
    ML_API_KEY = os.getenv('ML_API_KEY', '')
    ML_MODEL = os.getenv('ML_MODEL', 'gpt-5.5')
    ML_ENABLED = os.getenv('ML_ENABLED', '1') == '1'

    # ═══════════════════════════════════════════════════════════════════
    # LOGGING
    # ═══════════════════════════════════════════════════════════════════
    LOG_FILE = os.getenv('LOG_FILE', 'weather_bot.log')
    LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO')

    # ═══════════════════════════════════════════════════════════════════
    # REFERENCE TRADERS (for analysis)
    # ═══════════════════════════════════════════════════════════════════
    REFERENCE_TRADERS = [
        '0x594edb9112f526fa6a80b8f858a6379c8a2c1c11',
        '0x331bf91c132af9d921e1908ca0979363fc47193f',
        '0x15ceffed7bf820cd2d90f90ea24ae9909f5cd5fa',
    ]

    # ═══════════════════════════════════════════════════════════════════
    # HELPERS
    # ═══════════════════════════════════════════════════════════════════
    @classmethod
    def is_paper(cls) -> bool:
        return cls.TRADING_MODE.lower() == 'paper'

    @classmethod
    def is_live(cls) -> bool:
        return cls.TRADING_MODE.lower() == 'live'

    @classmethod
    def get_clob_url(cls) -> str:
        return cls.CLOB_API_URL

    @classmethod
    def print_status(cls):
        mode = '📋 PAPER (DRY-RUN)' if cls.is_paper() else '🔴 LIVE'
        print(f"\n{'='*60}")
        print(f"🌤️  WEATHER SNIPER v{cls.VERSION} — {cls.VERSION_NAME}")
        print(f"{'='*60}")
        print(f"Mode:       {mode}")
        print(f"Balance:    ${cls.STARTING_BALANCE:.2f} pUSD")
        print(f"Max Entry:  ${cls.SNIPER_MAX_ENTRY_PRICE:.2f}")
        print(f"Min Edge:   {cls.MIN_EDGE_TO_ENTER*100:.0f}%")
        print(f"Kelly:      {cls.KELLY_FRACTION}")
        print(f"Spread:     {'ON' if cls.SPREAD_ENABLED else 'OFF'}")
        print(f"Scan:       every {cls.SCAN_INTERVAL_SECONDS}s")
        print(f"{'='*60}\n")
