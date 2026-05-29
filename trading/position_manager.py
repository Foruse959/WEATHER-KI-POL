"""
Position Manager — Track, monitor, and redeem positions.

Features:
- Track all open positions with entry price, size, current value
- Auto-detect resolved markets (check if market closed)
- Redeem winning positions (claim pUSD payout)
- Calculate real-time PnL across portfolio
- Monitor reference trader positions for intelligence
"""

import os
import json
import time
import requests
from typing import Dict, List, Optional, Tuple
from datetime import datetime, timezone
from dataclasses import dataclass, field

from config import Config
from logger import log


@dataclass
class TrackedPosition:
    """A position being tracked by the bot."""
    id: str
    market_title: str
    bucket_label: str
    token_id: str
    condition_id: str
    entry_price: float
    shares: float
    cost_usd: float
    current_price: float
    current_value: float
    entry_time: datetime
    resolution_time: Optional[datetime]
    strategy: str
    status: str = 'open'         # open, won, lost, redeemed, sold
    pnl: float = 0.0
    redeemable: bool = False
    city: str = ''
    slug: str = ''

    @property
    def unrealized_pnl(self) -> float:
        if self.status == 'open':
            return self.current_value - self.cost_usd
        return self.pnl

    @property
    def roi_pct(self) -> float:
        if self.cost_usd <= 0:
            return 0
        return (self.unrealized_pnl / self.cost_usd) * 100


class PositionManager:
    """Manage positions with balance tracking and redemption."""

    def __init__(self):
        self.positions: List[TrackedPosition] = []
        self.paper_balance = Config.STARTING_BALANCE
        self.total_deposited = Config.STARTING_BALANCE
        self.total_redeemed = 0.0
        self.total_trades = 0
        self.wins = 0
        self.losses = 0
        self._state_file = 'data/positions.json'
        self._session = requests.Session()
        self._load_state()

    # ═══════════════════════════════════════════════════════════════
    # BALANCE TRACKING
    # ═══════════════════════════════════════════════════════════════

    def get_balance(self) -> float:
        """Get current available balance (paper or live)."""
        if Config.is_paper():
            return self.paper_balance
        # Live: try on-chain
        return self._get_onchain_balance() or self.paper_balance

    def get_portfolio_value(self) -> float:
        """Total value: balance + open position values."""
        open_value = sum(p.current_value for p in self.positions if p.status == 'open')
        return self.get_balance() + open_value

    def get_total_pnl(self) -> float:
        """Total PnL across all positions (realized + unrealized)."""
        realized = sum(p.pnl for p in self.positions if p.status in ('won', 'lost', 'redeemed', 'sold'))
        unrealized = sum(p.unrealized_pnl for p in self.positions if p.status == 'open')
        return realized + unrealized

    def _get_onchain_balance(self) -> Optional[float]:
        """Check on-chain pUSD balance."""
        wallet = Config.POLY_PROXY_WALLET
        if not wallet:
            return None
        try:
            from data.clob_client import ClobClient
            return ClobClient.get_pusd_balance_static(wallet)
        except Exception:
            return None

    # ═══════════════════════════════════════════════════════════════
    # POSITION TRACKING
    # ═══════════════════════════════════════════════════════════════

    def add_position(self, token_id: str, condition_id: str, entry_price: float,
                     shares: float, cost_usd: float, market_title: str,
                     bucket_label: str, strategy: str, city: str = '',
                     slug: str = '', resolution_time: datetime = None) -> TrackedPosition:
        """Add a new position after trade execution."""
        pos = TrackedPosition(
            id=f"pos_{int(time.time())}_{self.total_trades}",
            market_title=market_title,
            bucket_label=bucket_label,
            token_id=token_id,
            condition_id=condition_id,
            entry_price=entry_price,
            shares=shares,
            cost_usd=cost_usd,
            current_price=entry_price,
            current_value=shares * entry_price,
            entry_time=datetime.now(timezone.utc),
            resolution_time=resolution_time,
            strategy=strategy,
            city=city,
            slug=slug,
        )
        self.positions.append(pos)
        self.total_trades += 1

        if Config.is_paper():
            self.paper_balance -= cost_usd

        self._save_state()
        log.info(f"📌 Position added: {bucket_label} | {shares:.0f} shares @ ${entry_price:.4f} | cost=${cost_usd:.2f}")
        return pos

    def get_open_positions(self) -> List[TrackedPosition]:
        """Get all open positions."""
        return [p for p in self.positions if p.status == 'open']

    def get_redeemable_positions(self) -> List[TrackedPosition]:
        """Get positions that can be redeemed (market resolved, we won)."""
        return [p for p in self.positions if p.redeemable and p.status in ('open', 'won')]

    # ═══════════════════════════════════════════════════════════════
    # PRICE UPDATES
    # ═══════════════════════════════════════════════════════════════

    def update_prices(self):
        """Update current prices for all open positions."""
        open_pos = self.get_open_positions()
        if not open_pos:
            return

        for pos in open_pos:
            try:
                resp = self._session.get(
                    f"{Config.CLOB_API_URL}/price",
                    params={'token_id': pos.token_id, 'side': 'SELL'},
                    timeout=5,
                )
                if resp.status_code == 200:
                    price = float(resp.json().get('price', pos.current_price))
                    pos.current_price = price
                    pos.current_value = pos.shares * price
            except Exception:
                pass

        self._save_state()

    # ═══════════════════════════════════════════════════════════════
    # RESOLUTION & REDEMPTION
    # ═══════════════════════════════════════════════════════════════

    def check_resolutions(self):
        """Check if any open positions have resolved (market closed)."""
        open_pos = self.get_open_positions()
        if not open_pos:
            return

        for pos in open_pos:
            try:
                # Check via data-api for our own positions
                # If curPrice is 1.0 → we won, if 0.0 → we lost
                resp = self._session.get(
                    f"{Config.CLOB_API_URL}/price",
                    params={'token_id': pos.token_id, 'side': 'SELL'},
                    timeout=5,
                )
                if resp.status_code == 200:
                    price = float(resp.json().get('price', 0))
                    if price >= 0.99:
                        # Won!
                        pos.status = 'won'
                        pos.redeemable = True
                        pos.current_price = 1.0
                        pos.current_value = pos.shares
                        pos.pnl = pos.shares - pos.cost_usd
                        self.wins += 1
                        log.info(f"✅ WON: {pos.bucket_label} | PnL=${pos.pnl:+.2f}")
                    elif price <= 0.01 and pos.resolution_time and \
                         datetime.now(timezone.utc) > pos.resolution_time:
                        # Lost
                        pos.status = 'lost'
                        pos.current_price = 0.0
                        pos.current_value = 0.0
                        pos.pnl = -pos.cost_usd
                        self.losses += 1
                        log.info(f"❌ LOST: {pos.bucket_label} | PnL=${pos.pnl:+.2f}")
                elif resp.status_code == 404:
                    # Market might be resolved
                    if pos.resolution_time and datetime.now(timezone.utc) > pos.resolution_time:
                        pos.status = 'lost'
                        pos.pnl = -pos.cost_usd
                        self.losses += 1
            except Exception:
                pass

        self._save_state()

    def redeem_position(self, pos: TrackedPosition) -> bool:
        """Redeem a winning position (claim pUSD)."""
        if not pos.redeemable:
            log.warning(f"Position {pos.id} not redeemable")
            return False

        if Config.is_paper():
            # Paper: just credit the balance
            payout = pos.shares * 1.0  # $1 per share on win
            self.paper_balance += payout
            pos.status = 'redeemed'
            pos.pnl = payout - pos.cost_usd
            self.total_redeemed += payout
            log.info(f"📋 PAPER REDEEM: {pos.bucket_label} → +${payout:.2f}")
            self._save_state()
            return True
        else:
            # Live: call CLOB redeem endpoint
            try:
                from data.clob_client import ClobClient
                client = ClobClient()
                success = client.redeem_position(pos.condition_id)
                if success:
                    pos.status = 'redeemed'
                    pos.pnl = pos.shares - pos.cost_usd
                    self.total_redeemed += pos.shares
                    log.info(f"💰 REDEEMED: {pos.bucket_label} → +${pos.shares:.2f}")
                    self._save_state()
                    return True
            except Exception as e:
                log.error(f"Redeem failed: {e}")
            return False

    def redeem_all_winning(self) -> int:
        """Redeem all redeemable positions."""
        redeemable = self.get_redeemable_positions()
        redeemed_count = 0
        for pos in redeemable:
            if self.redeem_position(pos):
                redeemed_count += 1
        return redeemed_count

    # ═══════════════════════════════════════════════════════════════
    # STATISTICS
    # ═══════════════════════════════════════════════════════════════

    def get_stats(self) -> Dict:
        """Get comprehensive trading statistics."""
        open_pos = self.get_open_positions()
        total_closed = self.wins + self.losses
        win_rate = (self.wins / max(1, total_closed)) * 100

        return {
            'mode': 'PAPER' if Config.is_paper() else 'LIVE',
            'balance': self.get_balance(),
            'portfolio_value': self.get_portfolio_value(),
            'total_pnl': self.get_total_pnl(),
            'roi_pct': (self.get_total_pnl() / max(0.01, self.total_deposited)) * 100,
            'total_trades': self.total_trades,
            'open_positions': len(open_pos),
            'wins': self.wins,
            'losses': self.losses,
            'win_rate': win_rate,
            'total_redeemed': self.total_redeemed,
            'avg_entry_price': (sum(p.entry_price for p in self.positions) /
                               max(1, len(self.positions))),
        }

    # ═══════════════════════════════════════════════════════════════
    # PERSISTENCE
    # ═══════════════════════════════════════════════════════════════

    def _save_state(self):
        """Save all positions and stats to disk."""
        try:
            os.makedirs('data', exist_ok=True)
            state = {
                'paper_balance': self.paper_balance,
                'total_deposited': self.total_deposited,
                'total_redeemed': self.total_redeemed,
                'total_trades': self.total_trades,
                'wins': self.wins,
                'losses': self.losses,
                'positions': [
                    {
                        'id': p.id, 'market_title': p.market_title,
                        'bucket_label': p.bucket_label, 'token_id': p.token_id,
                        'condition_id': p.condition_id, 'entry_price': p.entry_price,
                        'shares': p.shares, 'cost_usd': p.cost_usd,
                        'current_price': p.current_price,
                        'current_value': p.current_value,
                        'entry_time': p.entry_time.isoformat(),
                        'resolution_time': p.resolution_time.isoformat() if p.resolution_time else None,
                        'strategy': p.strategy, 'status': p.status,
                        'pnl': p.pnl, 'redeemable': p.redeemable,
                        'city': p.city, 'slug': p.slug,
                    }
                    for p in self.positions[-200:]
                ],
                'last_updated': datetime.now(timezone.utc).isoformat(),
            }
            with open(self._state_file, 'w') as f:
                json.dump(state, f, indent=2)
        except Exception as e:
            log.warning(f"Save state failed: {e}")

    def _load_state(self):
        """Load positions from disk."""
        try:
            if not os.path.exists(self._state_file):
                return
            with open(self._state_file, 'r') as f:
                state = json.load(f)
            self.paper_balance = state.get('paper_balance', Config.STARTING_BALANCE)
            self.total_deposited = state.get('total_deposited', Config.STARTING_BALANCE)
            self.total_redeemed = state.get('total_redeemed', 0)
            self.total_trades = state.get('total_trades', 0)
            self.wins = state.get('wins', 0)
            self.losses = state.get('losses', 0)
            for pd in state.get('positions', []):
                try:
                    pos = TrackedPosition(
                        id=pd['id'],
                        market_title=pd.get('market_title', ''),
                        bucket_label=pd.get('bucket_label', ''),
                        token_id=pd.get('token_id', ''),
                        condition_id=pd.get('condition_id', ''),
                        entry_price=pd.get('entry_price', 0),
                        shares=pd.get('shares', 0),
                        cost_usd=pd.get('cost_usd', 0),
                        current_price=pd.get('current_price', 0),
                        current_value=pd.get('current_value', 0),
                        entry_time=datetime.fromisoformat(pd['entry_time']),
                        resolution_time=datetime.fromisoformat(pd['resolution_time']) if pd.get('resolution_time') else None,
                        strategy=pd.get('strategy', ''),
                        status=pd.get('status', 'open'),
                        pnl=pd.get('pnl', 0),
                        redeemable=pd.get('redeemable', False),
                        city=pd.get('city', ''),
                        slug=pd.get('slug', ''),
                    )
                    self.positions.append(pos)
                except Exception:
                    continue
            log.info(f"Loaded {len(self.positions)} positions from disk")
        except Exception as e:
            log.debug(f"No saved state: {e}")
