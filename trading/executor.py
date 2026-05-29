"""
Trading Executor — Paper + Live order execution.

Paper mode: Simulates trades, tracks PnL, no real orders.
Live mode: Places real orders on Polymarket CLOB (reuses auth from polymarket-bot-v2).

Supports:
- GTC limit orders (maker, 0% fee)
- FOK market orders (taker, small fee)
- Position tracking and PnL calculation
"""

import time
import json
import os
import requests
from typing import Dict, List, Optional
from datetime import datetime, timezone
from dataclasses import dataclass, field, asdict

from config import Config
from logger import log


@dataclass
class Position:
    """An active trading position."""
    id: str
    market_title: str
    bucket_label: str
    token_id: str
    side: str              # 'BUY'
    entry_price: float
    shares: float
    cost_usd: float
    timestamp: datetime
    strategy: str          # 'sniper' or 'spread'
    status: str = 'open'   # 'open', 'won', 'lost', 'sold'
    exit_price: Optional[float] = None
    pnl: float = 0.0


@dataclass
class PaperAccount:
    """Simulated account for paper trading."""
    balance: float
    positions: List[Position] = field(default_factory=list)
    trade_history: List[Dict] = field(default_factory=list)
    total_trades: int = 0
    wins: int = 0
    losses: int = 0
    total_pnl: float = 0.0


class TradingExecutor:
    """Execute trades in paper or live mode."""

    def __init__(self):
        self.is_paper = Config.is_paper()
        self.paper_account = PaperAccount(balance=Config.STARTING_BALANCE)
        self._clob_client = None
        self._session = requests.Session()
        self._session.headers.update({'User-Agent': f'WeatherSniper/{Config.VERSION}'})
        self._positions_file = 'data/positions.json'
        self._load_state()

        if self.is_paper:
            log.info(f"📋 PAPER MODE — Starting balance: ${Config.STARTING_BALANCE:.2f}")
        else:
            log.info(f"🔴 LIVE MODE — Connecting to CLOB...")
            self._init_live()

    def _init_live(self):
        """Initialize CLOB client for live trading."""
        if not Config.POLY_PRIVATE_KEY:
            log.error("❌ No POLY_PRIVATE_KEY set — cannot trade live!")
            log.info("💡 Set TRADING_MODE=paper in .env for dry-run")
            return

        try:
            from data.clob_client import ClobClient
            self._clob_client = ClobClient()
            self._clob_client.init_py_clob_client(
                private_key=Config.POLY_PRIVATE_KEY,
                funder=Config.POLY_FUNDER_ADDRESS or None,
                signature_type=Config.POLY_SIGNATURE_TYPE,
            )
            log.info("✅ CLOB client initialized for live trading")
        except Exception as e:
            log.error(f"❌ CLOB init failed: {e}")
            log.info("⚠️  Falling back to paper mode")
            self.is_paper = True

    def get_balance(self) -> float:
        """Get current balance."""
        if self.is_paper:
            return self.paper_account.balance
        # Live: check on-chain balance
        if self._clob_client:
            try:
                bal = self._clob_client.get_pusd_balance_onchain(
                    Config.POLY_PROXY_WALLET or Config.derive_wallet_address()
                )
                if bal is not None:
                    return bal
            except Exception:
                pass
        return Config.STARTING_BALANCE

    def get_open_positions(self) -> List[Position]:
        """Get all open positions."""
        return [p for p in self.paper_account.positions if p.status == 'open']

    def place_buy(
        self,
        token_id: str,
        price: float,
        size_usd: float,
        market_title: str = '',
        bucket_label: str = '',
        strategy: str = 'sniper',
    ) -> Optional[Position]:
        """
        Place a BUY order (paper or live).
        
        Args:
            token_id: CLOB token ID for the outcome
            price: limit price (e.g. 0.07 for 7¢)
            size_usd: how much to spend in USD
            market_title: for logging
            bucket_label: outcome label
            strategy: 'sniper' or 'spread'
        
        Returns:
            Position if successful, None if failed
        """
        # Pre-checks
        balance = self.get_balance()
        if size_usd > balance:
            log.warning(f"⚠️  Insufficient balance: ${size_usd:.2f} > ${balance:.2f}")
            size_usd = balance * 0.95  # use 95% of what's available

        if size_usd < Config.MIN_ORDER_SIZE and not self.is_paper:
            log.warning(f"⚠️  Order too small: ${size_usd:.2f} < ${Config.MIN_ORDER_SIZE}")
            return None

        shares = size_usd / price if price > 0 else 0
        if shares <= 0:
            return None

        # Check position limits
        open_positions = self.get_open_positions()
        if len(open_positions) >= Config.MAX_POSITIONS:
            log.warning(f"⚠️  Max positions ({Config.MAX_POSITIONS}) reached")
            return None

        if self.is_paper:
            return self._paper_buy(token_id, price, size_usd, shares,
                                   market_title, bucket_label, strategy)
        else:
            return self._live_buy(token_id, price, size_usd, shares,
                                  market_title, bucket_label, strategy)

    def _paper_buy(self, token_id, price, size_usd, shares,
                   market_title, bucket_label, strategy) -> Optional[Position]:
        """Simulate a buy in paper mode."""
        self.paper_account.balance -= size_usd
        self.paper_account.total_trades += 1

        pos_id = f"paper_{int(time.time())}_{self.paper_account.total_trades}"
        position = Position(
            id=pos_id,
            market_title=market_title,
            bucket_label=bucket_label,
            token_id=token_id,
            side='BUY',
            entry_price=price,
            shares=shares,
            cost_usd=size_usd,
            timestamp=datetime.now(timezone.utc),
            strategy=strategy,
        )
        self.paper_account.positions.append(position)
        self._save_state()

        log.info(
            f"📋 PAPER BUY: {bucket_label} @ ${price:.4f} | "
            f"${size_usd:.2f} → {shares:.1f} shares | "
            f"Strategy: {strategy} | Balance: ${self.paper_account.balance:.2f}"
        )
        return position


    def _live_buy(self, token_id, price, size_usd, shares,
                  market_title, bucket_label, strategy) -> Optional[Position]:
        """Place a real order on Polymarket CLOB."""
        if not self._clob_client:
            log.error("❌ CLOB client not available")
            return None

        try:
            # Try GTC limit order (maker = 0% fee)
            result = self._clob_client.place_limit_order(
                token_id=token_id,
                side='BUY',
                price=price,
                size_pusd=size_usd,
                expiration='GTC',
            )

            if result:
                status = (result.get('status') or '').upper()
                log.info(f"🔴 LIVE BUY: {bucket_label} @ ${price:.4f} | "
                         f"${size_usd:.2f} | Status: {status}")

                pos_id = result.get('orderID', f"live_{int(time.time())}")
                position = Position(
                    id=pos_id,
                    market_title=market_title,
                    bucket_label=bucket_label,
                    token_id=token_id,
                    side='BUY',
                    entry_price=price,
                    shares=shares,
                    cost_usd=size_usd,
                    timestamp=datetime.now(timezone.utc),
                    strategy=strategy,
                )
                self.paper_account.positions.append(position)
                self.paper_account.total_trades += 1
                self._save_state()
                return position
            else:
                log.warning(f"⚠️  Order returned None for {bucket_label}")
                return None

        except Exception as e:
            log.error(f"❌ Live order failed: {e}")
            return None

    def resolve_position(self, position: Position, won: bool):
        """Mark a position as resolved (market settled)."""
        if won:
            payout = position.shares * 1.0  # binary: $1 per share
            position.pnl = payout - position.cost_usd
            position.status = 'won'
            position.exit_price = 1.0
            self.paper_account.wins += 1
            if self.is_paper:
                self.paper_account.balance += payout
        else:
            position.pnl = -position.cost_usd
            position.status = 'lost'
            position.exit_price = 0.0
            self.paper_account.losses += 1

        self.paper_account.total_pnl += position.pnl
        self._save_state()

        emoji = '✅' if won else '❌'
        log.info(
            f"{emoji} Position resolved: {position.bucket_label} | "
            f"PnL: ${position.pnl:+.2f} | "
            f"Total PnL: ${self.paper_account.total_pnl:+.2f}"
        )

    def get_stats(self) -> Dict:
        """Get trading statistics."""
        total = self.paper_account.total_trades
        wins = self.paper_account.wins
        losses = self.paper_account.losses
        open_count = len(self.get_open_positions())

        return {
            'mode': 'PAPER' if self.is_paper else 'LIVE',
            'balance': self.get_balance(),
            'total_trades': total,
            'wins': wins,
            'losses': losses,
            'win_rate': (wins / max(1, wins + losses)) * 100,
            'open_positions': open_count,
            'total_pnl': self.paper_account.total_pnl,
            'roi_pct': (self.paper_account.total_pnl / Config.STARTING_BALANCE) * 100,
        }

    def _save_state(self):
        """Persist positions to disk."""
        try:
            os.makedirs('data', exist_ok=True)
            state = {
                'balance': self.paper_account.balance,
                'total_trades': self.paper_account.total_trades,
                'wins': self.paper_account.wins,
                'losses': self.paper_account.losses,
                'total_pnl': self.paper_account.total_pnl,
                'positions': [
                    {
                        'id': p.id, 'market_title': p.market_title,
                        'bucket_label': p.bucket_label, 'token_id': p.token_id,
                        'side': p.side, 'entry_price': p.entry_price,
                        'shares': p.shares, 'cost_usd': p.cost_usd,
                        'timestamp': p.timestamp.isoformat(),
                        'strategy': p.strategy, 'status': p.status,
                        'exit_price': p.exit_price, 'pnl': p.pnl,
                    }
                    for p in self.paper_account.positions[-100:]  # keep last 100
                ],
            }
            with open(self._positions_file, 'w') as f:
                json.dump(state, f, indent=2)
        except Exception as e:
            log.warning(f"Could not save state: {e}")

    def _load_state(self):
        """Load positions from disk."""
        try:
            if os.path.exists(self._positions_file):
                with open(self._positions_file, 'r') as f:
                    state = json.load(f)
                self.paper_account.balance = state.get('balance', Config.STARTING_BALANCE)
                self.paper_account.total_trades = state.get('total_trades', 0)
                self.paper_account.wins = state.get('wins', 0)
                self.paper_account.losses = state.get('losses', 0)
                self.paper_account.total_pnl = state.get('total_pnl', 0)
                for p_data in state.get('positions', []):
                    try:
                        pos = Position(
                            id=p_data['id'],
                            market_title=p_data.get('market_title', ''),
                            bucket_label=p_data.get('bucket_label', ''),
                            token_id=p_data.get('token_id', ''),
                            side=p_data.get('side', 'BUY'),
                            entry_price=p_data.get('entry_price', 0),
                            shares=p_data.get('shares', 0),
                            cost_usd=p_data.get('cost_usd', 0),
                            timestamp=datetime.fromisoformat(p_data.get('timestamp', '')),
                            strategy=p_data.get('strategy', 'sniper'),
                            status=p_data.get('status', 'open'),
                            exit_price=p_data.get('exit_price'),
                            pnl=p_data.get('pnl', 0),
                        )
                        self.paper_account.positions.append(pos)
                    except Exception:
                        continue
                log.info(f"Loaded {len(self.paper_account.positions)} positions from disk")
        except Exception as e:
            log.debug(f"No saved state: {e}")
