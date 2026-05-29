"""
Weather Sniper Bot — Main Dashboard / Trading Loop

Flow:
1. Scan Polymarket for active weather markets
2. For each market: fetch multi-source forecasts
3. Run probability engine → find mispriced buckets
4. Run strategies (Sniper + Spread) → generate signals
5. Execute trades (paper or live)
6. Monitor positions → log results

Usage:
    python dashboard.py              # paper mode (default)
    python dashboard.py --live       # live trading
    python dashboard.py --once       # single scan then exit
"""

import sys
import time
import argparse
from datetime import datetime, timezone

from config import Config
from logger import log
from data.weather_fetcher import WeatherFetcher, get_city_coords
from data.probability_engine import ProbabilityEngine
from data.market_scanner import MarketScanner
from strategies.sniper_strategy import SniperStrategy
from strategies.spread_strategy import SpreadStrategy
from trading.executor import TradingExecutor


class WeatherBot:
    """Main weather trading bot."""

    def __init__(self):
        self.fetcher = WeatherFetcher()
        self.engine = ProbabilityEngine()
        self.scanner = MarketScanner()
        self.sniper = SniperStrategy()
        self.spread = SpreadStrategy()
        self.executor = TradingExecutor()
        self.scan_count = 0
        self.signals_generated = 0
        self.trades_placed = 0

    def run_once(self):
        """Run a single scan cycle."""
        self.scan_count += 1
        log.info(f"\n{'═'*60}")
        log.info(f"🔍 SCAN #{self.scan_count} — {datetime.now(timezone.utc).strftime('%H:%M:%S UTC')}")
        log.info(f"{'═'*60}")

        # Step 1: Discover weather markets
        markets = self.scanner.scan_weather_markets()
        if not markets:
            log.info("No active weather markets found. Waiting...")
            return

        log.info(f"Found {len(markets)} active weather markets")

        # Step 2: Evaluate each market
        for market in markets:
            try:
                self._evaluate_market(market)
            except Exception as e:
                log.error(f"Error evaluating {market.title}: {e}")
                continue

        # Step 3: Print status
        self._print_status()


    def _evaluate_market(self, market):
        """Evaluate a single weather market for trading opportunities."""
        city = market.city
        if city == 'Unknown':
            log.debug(f"Skipping unknown-location market: {market.title}")
            return

        # Get coordinates for this city
        coords = get_city_coords(city)
        if not coords:
            log.debug(f"No coordinates for city: {city}")
            return

        lat, lon = coords

        # Fetch forecasts
        target_time = market.resolution_time
        forecasts = self.fetcher.fetch_all(lat, lon, city, target_time)
        if not forecasts:
            log.warning(f"No forecasts for {city}")
            return

        # Build bucket list from market outcomes
        buckets = []
        token_ids = {}
        for outcome in market.outcomes:
            label = outcome['label']
            lo = outcome.get('bucket_low', float('-inf'))
            hi = outcome.get('bucket_high', float('inf'))
            buckets.append((label, lo, hi))
            token_ids[label] = outcome.get('token_id', '')

        if not buckets:
            return

        # Run probability engine
        bucket_probs = self.engine.estimate_bucket_probabilities(
            forecasts, buckets, target_time
        )

        # Get live market prices
        market_prices = self.scanner.get_outcome_prices(market)
        if not market_prices:
            # Use cached prices from scan
            market_prices = {o['label']: o.get('price', 0.5) for o in market.outcomes}

        balance = self.executor.get_balance()

        # Run Sniper Strategy
        sniper_signals = self.sniper.evaluate(
            market.title, bucket_probs, market_prices, token_ids, balance
        )

        for signal in sniper_signals[:3]:  # top 3 signals per market
            self.signals_generated += 1
            log.info(f"🎯 SNIPER: {signal.bucket_label} @ ${signal.market_price:.4f} | "
                     f"Edge={signal.edge:.1%} | EV={signal.expected_return:.0f}x")

            # Execute trade
            position = self.executor.place_buy(
                token_id=signal.token_id,
                price=signal.market_price,
                size_usd=signal.kelly_size,
                market_title=market.title,
                bucket_label=signal.bucket_label,
                strategy='sniper',
            )
            if position:
                self.trades_placed += 1

        # Run Spread Strategy
        spread_signals = self.spread.evaluate(
            market.title, bucket_probs, market_prices, token_ids, balance
        )

        for signal in spread_signals[:1]:  # max 1 spread per market
            self.signals_generated += 1
            log.info(f"📊 SPREAD: {signal.primary_bucket} | "
                     f"{len(signal.legs)} legs | Cost=${signal.total_cost:.2f} | "
                     f"EV=${signal.expected_payout:.2f}")

            # Execute each leg
            for leg in signal.legs:
                position = self.executor.place_buy(
                    token_id=leg.token_id,
                    price=leg.market_price,
                    size_usd=leg.size_usd,
                    market_title=market.title,
                    bucket_label=leg.bucket_label,
                    strategy='spread',
                )
                if position:
                    self.trades_placed += 1

    def _print_status(self):
        """Print current bot status."""
        stats = self.executor.get_stats()
        log.info(f"\n{'─'*40}")
        log.info(f"📊 STATUS — Scan #{self.scan_count}")
        log.info(f"   Mode:       {stats['mode']}")
        log.info(f"   Balance:    ${stats['balance']:.2f}")
        log.info(f"   Trades:     {stats['total_trades']}")
        log.info(f"   Win Rate:   {stats['win_rate']:.1f}%")
        log.info(f"   Open Pos:   {stats['open_positions']}")
        log.info(f"   Total PnL:  ${stats['total_pnl']:+.2f}")
        log.info(f"   ROI:        {stats['roi_pct']:+.1f}%")
        log.info(f"{'─'*40}\n")

    def run_loop(self):
        """Main trading loop — runs until interrupted."""
        Config.print_status()
        log.info("🚀 Weather Sniper Bot starting...")
        log.info(f"   Scan interval: {Config.SCAN_INTERVAL_SECONDS}s")
        log.info(f"   Strategies: Sniper + {'Spread' if Config.SPREAD_ENABLED else '(Spread OFF)'}")
        log.info("")

        try:
            while True:
                try:
                    self.run_once()
                except KeyboardInterrupt:
                    raise
                except Exception as e:
                    log.error(f"Scan error: {e}")

                # Wait for next scan
                log.info(f"⏳ Next scan in {Config.SCAN_INTERVAL_SECONDS}s...")
                time.sleep(Config.SCAN_INTERVAL_SECONDS)

        except KeyboardInterrupt:
            log.info("\n🛑 Bot stopped by user")
            self._print_status()


def main():
    parser = argparse.ArgumentParser(description='Weather Sniper Bot')
    parser.add_argument('--live', action='store_true', help='Enable live trading')
    parser.add_argument('--paper', action='store_true', help='Paper/dry-run mode (default)')
    parser.add_argument('--once', action='store_true', help='Run single scan then exit')
    parser.add_argument('--balance', type=float, help='Override starting balance')
    args = parser.parse_args()

    if args.live:
        Config.TRADING_MODE = 'live'
    if args.balance:
        Config.STARTING_BALANCE = args.balance

    bot = WeatherBot()

    if args.once:
        bot.run_once()
        bot._print_status()
    else:
        bot.run_loop()


if __name__ == '__main__':
    main()
