"""
Multi-Outcome Spread Strategy — Buy multiple adjacent buckets.

Strategy: When forecast points to a specific temperature, buy:
- Primary bucket (heaviest position)
- Adjacent buckets with decaying size

Example: Forecast says 25°C
- Buy "25°C" at 60% of position
- Buy "24°C" at 25% of position  
- Buy "26°C" at 15% of position

This way we profit even if the actual temp is ±1°C from forecast.
The key is to only do this when the SUM of what we pay < expected payout.
"""

from typing import Dict, List, Optional
from dataclasses import dataclass

from config import Config
from data.probability_engine import BucketProbability
from logger import log


@dataclass
class SpreadLeg:
    """A single leg of a spread position."""
    bucket_label: str
    token_id: str
    market_price: float
    our_probability: float
    allocation_pct: float  # what % of total spread budget
    size_usd: float


@dataclass
class SpreadSignal:
    """A multi-outcome spread trade signal."""
    market_title: str
    primary_bucket: str
    legs: List[SpreadLeg]
    total_cost: float
    expected_payout: float
    expected_profit: float
    win_probability: float  # P(any leg resolves YES)
    confidence: float
    reason: str


class SpreadStrategy:
    """
    Buy multiple adjacent temperature buckets with decaying allocation.
    
    Entry criteria:
    1. Strong forecast pointing to a specific temperature
    2. Adjacent buckets are reasonably priced (sum < expected payout)
    3. At least 3 models agree on forecast
    4. Total spread cost within budget
    
    Sizing:
    - Primary bucket: 60% of budget
    - Adjacent ±1: 25% each (or neighbor_decay of primary)
    - Adjacent ±2: 15% each (if available and cheap)
    """

    def __init__(self):
        self.enabled = Config.SPREAD_ENABLED
        self.decay = Config.SPREAD_NEIGHBOR_DECAY
        self.max_cost = Config.SPREAD_MAX_COST

    def evaluate(
        self,
        market_title: str,
        bucket_probs: List[BucketProbability],
        market_prices: Dict[str, float],
        token_ids: Dict[str, str],
        balance: float,
    ) -> List[SpreadSignal]:
        """
        Find spread opportunities across adjacent buckets.
        """
        if not self.enabled:
            return []

        signals = []

        # Sort buckets by their temperature bounds
        sorted_buckets = sorted(bucket_probs, key=lambda b: b.bucket_low)

        # Find the primary bucket (highest probability)
        if not sorted_buckets:
            return []

        primary = max(sorted_buckets, key=lambda b: b.probability)
        primary_idx = sorted_buckets.index(primary)

        # Need strong signal on primary
        primary_price = market_prices.get(primary.bucket_label, 1.0)
        if primary.probability < 0.25:  # need decent probability
            return []
        if primary.n_models < 3:  # need model agreement
            return []

        # Budget for spread
        budget = min(self.max_cost, balance * Config.MAX_BET_PCT)
        if budget < Config.MIN_ORDER_SIZE:
            return []

        # Build legs
        legs = []
        allocations = self._calculate_allocations(
            sorted_buckets, primary_idx, market_prices, token_ids
        )

        total_cost = 0
        for label, alloc_pct in allocations:
            price = market_prices.get(label, 1.0)
            tid = token_ids.get(label)
            if not tid or price >= 0.90:  # skip if too expensive
                continue
            size = budget * alloc_pct
            if size < 0.10:  # skip tiny legs
                continue
            legs.append(SpreadLeg(
                bucket_label=label,
                token_id=tid,
                market_price=price,
                our_probability=next(
                    (b.probability for b in sorted_buckets if b.bucket_label == label), 0
                ),
                allocation_pct=alloc_pct,
                size_usd=size,
            ))
            total_cost += size * price

        if len(legs) < 2:  # need at least 2 legs for a spread
            return []

        # Expected payout: P(any leg wins) × $1.00 per winning share
        # Actually each leg independently pays out if its bucket resolves YES
        # So expected payout = sum(P(bucket_i) × shares_i)
        expected_payout = sum(
            leg.our_probability * (leg.size_usd / leg.market_price)
            for leg in legs if leg.market_price > 0
        )
        expected_profit = expected_payout - total_cost

        # Combined win probability (at least one leg hits)
        win_prob = 1.0 - 1.0
        for leg in legs:
            win_prob = 1.0 - (1.0 - win_prob) * (1.0 - leg.our_probability)
        # Actually simpler: P(primary wins) + P(neighbors win)
        win_prob = sum(leg.our_probability for leg in legs)
        win_prob = min(0.99, win_prob)

        if expected_profit <= 0:
            return []

        confidence = primary.confidence * min(1.0, primary.n_models / 4)

        reason = (
            f"Spread on {primary.bucket_label} "
            f"(forecast={primary.mean_forecast:.1f}°C) | "
            f"{len(legs)} legs | cost=${total_cost:.2f} → "
            f"EV=${expected_payout:.2f} | P(win)={win_prob:.0%}"
        )

        signals.append(SpreadSignal(
            market_title=market_title,
            primary_bucket=primary.bucket_label,
            legs=legs,
            total_cost=total_cost,
            expected_payout=expected_payout,
            expected_profit=expected_profit,
            win_probability=win_prob,
            confidence=confidence,
            reason=reason,
        ))

        return signals

    def _calculate_allocations(
        self,
        sorted_buckets: List[BucketProbability],
        primary_idx: int,
        market_prices: Dict[str, float],
        token_ids: Dict[str, str],
    ) -> List[tuple]:
        """
        Calculate allocation percentages for each leg.
        Primary gets 60%, neighbors decay by self.decay factor.
        """
        allocations = []
        n = len(sorted_buckets)
        primary = sorted_buckets[primary_idx]

        # Primary: 60%
        allocations.append((primary.bucket_label, 0.60))

        # ±1 neighbors: 25% each (capped by decay)
        if primary_idx - 1 >= 0:
            neighbor = sorted_buckets[primary_idx - 1]
            if token_ids.get(neighbor.bucket_label):
                allocations.append((neighbor.bucket_label, 0.60 * self.decay))

        if primary_idx + 1 < n:
            neighbor = sorted_buckets[primary_idx + 1]
            if token_ids.get(neighbor.bucket_label):
                allocations.append((neighbor.bucket_label, 0.60 * self.decay))

        # Normalize to sum = 1.0
        total_alloc = sum(a[1] for a in allocations)
        if total_alloc > 0:
            allocations = [(label, pct / total_alloc) for label, pct in allocations]

        return allocations
