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

    VERSION = "2.0.0"
    VERSION_NAME = "Weather Sniper Pro"

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

    # ═══════════════════════════════════════════════════════════════════
    # BUILDER RELAYER (required for live V2 trading)
    # ═══════════════════════════════════════════════════════════════════
    POLY_BUILDER_API_KEY = os.getenv('POLY_BUILDER_API_KEY', '')
    POLY_BUILDER_SECRET = os.getenv('POLY_BUILDER_SECRET', '')
    POLY_BUILDER_PASSPHRASE = os.getenv('POLY_BUILDER_PASSPHRASE', '')
    POLY_BUILDER_CODE = os.getenv('POLY_BUILDER_CODE', '')
    AUTO_REDEEM_INTERVAL = int(os.getenv('AUTO_REDEEM_INTERVAL', '120'))

    # ═══════════════════════════════════════════════════════════════════
    # V2 CONTRACT ADDRESSES (Polygon mainnet)
    # ═══════════════════════════════════════════════════════════════════
    PUSD_CONTRACT = '0xC011a7E12a19f7B1f670d46F03B03f3342E82DFB'
    CTF_EXCHANGE_V2 = '0xE111180000d2663C0091e4f400237545B87B996B'
    NEG_RISK_CTF_EXCHANGE = '0xe2222d279d744050d28e00520010520000310F59'

    # ═══════════════════════════════════════════════════════════════════
    # API ENDPOINTS (V2 — same as polymarket-bot-v2)
    # ═══════════════════════════════════════════════════════════════════
    GAMMA_API_URL = 'https://gamma-api.polymarket.com'
    CLOB_API_URL = 'https://clob.polymarket.com'
    POLYMARKET_WS_URL = 'wss://ws-subscriptions-clob.polymarket.com/ws/market'
    POLYGON_RPC_URL = os.getenv('POLYGON_RPC_URL', '')
    CLOB_RELAY_URL = os.getenv('CLOB_RELAY_URL', '')

    # Fee: weather = 0% maker (GTC), 5% taker (FOK)
    MAKER_FEE_RATE = 0.0
    TAKER_FEE_RATE = 0.05
    MAKER_PREFERRED = True  # always GTC limit = 0% fee

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
    # Risk Management (weather markets are BINARY → no traditional SL/TP)
    # Instead: hold to resolution OR sell early at profit
    # "Stop-loss" only applies to LOCK-IN trades that went wrong
    STOP_LOSS_PCT = float(os.getenv('STOP_LOSS_PCT', '-95'))  # almost never triggers
    TRAILING_STOP_PCT = float(os.getenv('TRAILING_STOP_PCT', '30'))
    # PROFIT-TAKE: sell if price rises above this BEFORE resolution (early profit)
    EARLY_PROFIT_THRESHOLD = float(os.getenv('EARLY_PROFIT_THRESHOLD', '0.60'))
    # For confident strategy: never sell (hold to resolution)
    CONFIDENT_NEVER_SELL = os.getenv('CONFIDENT_NEVER_SELL', '1') == '1'

    # ═══════════════════════════════════════════════════════════════════
    # FEATURE TOGGLES (enable/disable without breaking anything)
    # ═══════════════════════════════════════════════════════════════════
    SNIPER_ENABLED = os.getenv('SNIPER_ENABLED', '1') == '1'
    SPREAD_ENABLED = os.getenv('SPREAD_STRATEGY_ENABLED', '1') == '1'
    CONFIDENT_ENABLED = os.getenv('CONFIDENT_ENABLED', '1') == '1'
    LOCKIN_ENABLED = os.getenv('LOCKIN_ENABLED', '1') == '1'
    ML_ENABLED = os.getenv('ML_ENABLED', '1') == '1'
    TELEGRAM_ENABLED = os.getenv('TELEGRAM_ENABLED', '1') == '1'
    COPY_TRADING_ENABLED = os.getenv('COPY_TRADING_ENABLED', '0') == '1'
    ADAPTIVE_EXIT_ENABLED = os.getenv('ADAPTIVE_EXIT_ENABLED', '1') == '1'
    AUTO_REDEEM_ENABLED = os.getenv('AUTO_REDEEM_ENABLED', '1') == '1'
    DRAWDOWN_GATE_ENABLED = os.getenv('DRAWDOWN_GATE_ENABLED', '1') == '1'

    # ═══════════════════════════════════════════════════════════════════
    # CITY FILTER (which cities to trade — empty = all)
    # ═══════════════════════════════════════════════════════════════════
    ENABLED_CITIES = [c.strip() for c in os.getenv('ENABLED_CITIES', '').split(',') if c.strip()]
    # If empty → trade all cities. If set → only trade these.
    # Example: ENABLED_CITIES=tokyo,seoul,ankara,london

    # ═══════════════════════════════════════════════════════════════════
    # DRAWDOWN GATE — pause trading if drawdown exceeds threshold
    # ═══════════════════════════════════════════════════════════════════
    MAX_DAILY_DRAWDOWN_PCT = float(os.getenv('MAX_DAILY_DRAWDOWN_PCT', '30'))
    MAX_WEEKLY_DRAWDOWN_PCT = float(os.getenv('MAX_WEEKLY_DRAWDOWN_PCT', '50'))
    DRAWDOWN_COOLDOWN_MINUTES = int(os.getenv('DRAWDOWN_COOLDOWN_MINUTES', '60'))

    # ═══════════════════════════════════════════════════════════════════
    # LOCK-IN STRATEGY (buy near-certain outcomes at $0.90+ for safe profit)
    # ═══════════════════════════════════════════════════════════════════
    LOCKIN_MIN_PRICE = float(os.getenv('LOCKIN_MIN_PRICE', '0.90'))
    LOCKIN_MIN_CONFIDENCE = float(os.getenv('LOCKIN_MIN_CONFIDENCE', '0.85'))
    LOCKIN_MAX_BET_PCT = float(os.getenv('LOCKIN_MAX_BET_PCT', '0.40'))

    # ═══════════════════════════════════════════════════════════════════
    # ADAPTIVE EXIT — analyze unfavorable markets and exit properly
    # ═══════════════════════════════════════════════════════════════════
    ADAPTIVE_CHECK_INTERVAL = int(os.getenv('ADAPTIVE_CHECK_INTERVAL', '120'))
    ADAPTIVE_SELL_IF_EDGE_LOST = os.getenv('ADAPTIVE_SELL_IF_EDGE_LOST', '1') == '1'
    ADAPTIVE_MIN_HOLD_MINUTES = int(os.getenv('ADAPTIVE_MIN_HOLD_MINUTES', '10'))

    # ═══════════════════════════════════════════════════════════════════
    # COPY TRADING (mirror reference wallet trades)
    # ═══════════════════════════════════════════════════════════════════
    COPY_WALLET = os.getenv('COPY_WALLET', '0x594edb9112f526fa6a80b8f858a6379c8a2c1c11')
    COPY_SCALE_FACTOR = float(os.getenv('COPY_SCALE_FACTOR', '0.01'))
    COPY_POLL_INTERVAL = int(os.getenv('COPY_POLL_INTERVAL', '30'))

    # ═══════════════════════════════════════════════════════════════════
    # MULTI-OUTCOME SPREAD STRATEGY
    # ═══════════════════════════════════════════════════════════════════
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
    def is_live_ready(cls) -> bool:
        """Check if all credentials for live trading are set."""
        pk = cls.POLY_PRIVATE_KEY.strip() if cls.POLY_PRIVATE_KEY else ''
        return bool(pk)

    @classmethod
    def get_clob_url(cls) -> str:
        if cls.CLOB_RELAY_URL:
            return cls.CLOB_RELAY_URL.rstrip('/')
        return cls.CLOB_API_URL

    @classmethod
    def get_funder_address(cls) -> str:
        """Resolve funder address (same logic as polymarket-bot-v2)."""
        if cls.POLY_FUNDER_ADDRESS and cls.POLY_FUNDER_ADDRESS.strip():
            return cls.POLY_FUNDER_ADDRESS.strip()
        if cls.POLY_SIGNATURE_TYPE == 2:
            if cls.POLY_PROXY_WALLET and cls.POLY_PROXY_WALLET.strip():
                return cls.POLY_PROXY_WALLET.strip()
            return ''
        if cls.POLY_SIGNATURE_TYPE == 0:
            return cls.derive_wallet_address()
        return ''

    @classmethod
    def derive_wallet_address(cls) -> str:
        pk = cls.POLY_PRIVATE_KEY.strip() if cls.POLY_PRIVATE_KEY else ''
        if not pk:
            return ''
        try:
            from eth_account import Account
            if not pk.startswith('0x'):
                pk = '0x' + pk
            return Account.from_key(pk).address
        except Exception:
            return ''

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
