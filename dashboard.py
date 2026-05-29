"""
Weather Sniper Bot — Main Dashboard / Trading Loop

Flow:
1. Scan Polymarket for active weather markets (slug-based, confirmed pattern)
2. For each market: fetch multi-source forecasts
3. Run probability engine → find mispriced buckets
4. Run strategies (Sniper + Spread) → generate signals
5. Execute trades (paper or live)
6. Monitor positions, check resolutions, redeem winners
7. Send Telegram notifications

Usage:
    python dashboard.py              # paper mode (default)
    python dashboard.py --live       # live trading
    python dashboard.py --once       # single scan then exit
    python dashboard.py --status     # print status and exit
"""

import sys
import time
import argparse
from datetime import datetime, timezone

from config import Config
from logger import log
from data.weather_fetcher import WeatherFetcher, get_city_coords, CITY_COORDS
from data.probability_engine import ProbabilityEngine
from data.market_scanner import MarketScanner, MARKET_CITIES
from strategies.sniper_strategy import SniperStrategy
from strategies.spread_strategy import SpreadStrategy
from strategies.confident_strategy import ConfidentStrategy
from trading.position_manager import PositionManager
from bot.telegram_ui import TelegramBot
from ml.decision_engine import MLDecisionEngine


class WeatherBot:
    """Main weather trading bot with full dashboard."""

    def __init__(self):
        self.fetcher = WeatherFetcher()
        self.engine = ProbabilityEngine()
        self.scanner = MarketScanner()
        self.sniper = SniperStrategy()
        self.spread = SpreadStrategy()
        self.confident = ConfidentStrategy()
        self.pm = PositionManager()
        self.ml = MLDecisionEngine()
        self.telegram = TelegramBot(position_manager=self.pm, scanner=self.scanner)
        self.scan_count = 0
        self.signals_generated = 0
        self.trades_placed = 0
        self._last_resolution_check = 0
        self._last_daily_summary = ''
        self._last_weekly_record = ''

    def run_once(self):
        """Run a single scan cycle."""
        self.scan_count += 1
        now = datetime.now(timezone.utc)
        log.info(f"\n{'═'*60}")
        log.info(f"🔍 SCAN #{self.scan_count} — {now.strftime('%Y-%m-%d %H:%M:%S UTC')}")
        log.info(f"{'═'*60}")

        # Step 0: Check resolutions, risk triggers, redeem (every 5 minutes)
        if time.time() - self._last_resolution_check > 300:
            self._check_resolutions()
            self.pm.check_risk_triggers()  # stop-loss / take-profit
            self.pm.cleanup_contexts()     # free closed market memory
            self._last_resolution_check = time.time()

        # Weekly memory recording
        week_str = now.strftime('%Y-W%W')
        if week_str != self._last_weekly_record and now.weekday() == 0:
            self.pm.record_weekly_stats()
            self._last_weekly_record = week_str

        # Step 1: Discover weather markets
        markets = self.scanner.scan_weather_markets(days_ahead=Config.SCAN_DAYS_AHEAD)
        if not markets:
            log.info("No active weather markets found. Waiting...")
            return

        log.info(f"Found {len(markets)} active weather markets")

        # Step 2: Evaluate each market
        for market in markets:
            try:
                self._evaluate_market(market)
            except Exception as e:
                log.error(f"Error evaluating {market.title[:40]}: {e}")
                continue

        # Step 3: Update prices for open positions
        self.pm.update_prices()

        # Step 4: Print dashboard
        self._print_dashboard()

        # Step 5: Daily summary
        today_str = now.strftime('%Y-%m-%d')
        if today_str != self._last_daily_summary and now.hour >= 22:
            self.telegram.send_daily_summary()
            self._last_daily_summary = today_str

    def _evaluate_market(self, market):
        """Evaluate a single weather market for trading opportunities."""
        city = market.city
        city_lower = city.lower().replace(' ', '')

        # Get coordinates
        coords = get_city_coords(city)
        if not coords:
            # Try without spaces and common variants
            for key, val in CITY_COORDS.items():
                if city_lower in key.replace(' ', '') or key.replace(' ', '') in city_lower:
                    coords = val
                    break
        if not coords:
            log.debug(f"No coordinates for: {city}")
            return

        lat, lon = coords

        # Fetch forecasts
        target_time = market.resolution_time
        forecasts = self.fetcher.fetch_all(lat, lon, city, target_time)
        if not forecasts:
            log.debug(f"No forecasts for {city}")
            return

        # Build bucket list from outcomes
        buckets = []
        token_ids = {}
        condition_ids = {}
        for outcome in market.outcomes:
            label = outcome['label']
            lo = outcome.get('bucket_low', float('-inf'))
            hi = outcome.get('bucket_high', float('inf'))
            buckets.append((label, lo, hi))
            token_ids[label] = outcome.get('token_id', '')
            condition_ids[label] = outcome.get('condition_id', '')

        if not buckets:
            return

        # Run probability engine
        bucket_probs = self.engine.estimate_bucket_probabilities(
            forecasts, buckets, target_time
        )

        # Get market prices (from scan data, already fetched)
        market_prices = {o['label']: o.get('price', 0.5) for o in market.outcomes}

        balance = self.pm.get_balance()

        # Run Sniper Strategy
        sniper_signals = self.sniper.evaluate(
            market.title, bucket_probs, market_prices, token_ids, balance
        )

        for signal in sniper_signals[:2]:  # top 2 per market
            self.signals_generated += 1

            # ML VALIDATION: ask GPT-5.5 if we should take this trade
            ml_result = self.ml.validate_signal(
                city=city, bucket_label=signal.bucket_label,
                entry_price=signal.market_price, our_prob=signal.our_probability,
                edge=signal.edge, forecast_temp=signal.reason.split('=')[1].split('°')[0] if '=' in signal.reason else 0,
                n_models=3,
                weekly_context=self.pm.get_weekly_summary(),
            )

            if ml_result['action'] == 'SKIP' and ml_result['confidence'] > 0.7:
                log.info(f"🧠 ML SKIP: {signal.bucket_label} — {ml_result['reason']}")
                continue

            log.info(
                f"🎯 SNIPER: {city} | {signal.bucket_label[:30]} @ "
                f"${signal.market_price:.4f} | Edge={signal.edge:.1%} | "
                f"EV={signal.expected_return:.0f}x | ML={ml_result['action']}({ml_result['confidence']:.0%})"
            )

            # Execute
            pos = self.pm.add_position(
                token_id=signal.token_id,
                condition_id=condition_ids.get(signal.bucket_label, ''),
                entry_price=signal.market_price,
                shares=signal.kelly_size / signal.market_price if signal.market_price > 0 else 0,
                cost_usd=signal.kelly_size,
                market_title=market.title,
                bucket_label=signal.bucket_label,
                strategy='sniper',
                city=city,
                slug=market.slug,
                resolution_time=market.resolution_time,
            )
            if pos:
                self.trades_placed += 1
                self.telegram.notify_trade(
                    'BUY', signal.bucket_label, signal.market_price,
                    signal.kelly_size, pos.shares, 'sniper',
                    edge=signal.edge, city=city,
                )

        # Run Spread Strategy (89% WR — PRIMARY for safety)
        if Config.SPREAD_ENABLED:
            spread_signals = self.spread.evaluate(
                market.title, bucket_probs, market_prices, token_ids, balance
            )

            for signal in spread_signals[:1]:
                self.signals_generated += 1
                log.info(
                    f"📊 SPREAD: {city} | {signal.primary_bucket[:25]} | "
                    f"{len(signal.legs)} legs | Cost=${signal.total_cost:.2f}"
                )
                for leg in signal.legs:
                    pos = self.pm.add_position(
                        token_id=leg.token_id,
                        condition_id=condition_ids.get(leg.bucket_label, ''),
                        entry_price=leg.market_price,
                        shares=leg.size_usd / leg.market_price if leg.market_price > 0 else 0,
                        cost_usd=leg.size_usd,
                        market_title=market.title,
                        bucket_label=leg.bucket_label,
                        strategy='spread',
                        city=city,
                        slug=market.slug,
                        resolution_time=market.resolution_time,
                    )
                    if pos:
                        self.trades_placed += 1

        # Run Confident Predictor (45% WR, highest PnL — buy most-likely bucket)
        confident_signals = self.confident.evaluate(
            market.title, bucket_probs, market_prices, token_ids, balance
        )

        for signal in confident_signals[:1]:  # top 1 per market
            self.signals_generated += 1
            log.info(
                f"💎 CONFIDENT: {city} | {signal.bucket_label[:25]} @ "
                f"${signal.market_price:.3f} | P={signal.our_probability:.0%} | "
                f"Edge={signal.edge:.0%} | EV={signal.expected_return:.0f}x"
            )

            pos = self.pm.add_position(
                token_id=signal.token_id,
                condition_id=condition_ids.get(signal.bucket_label, ''),
                entry_price=signal.market_price,
                shares=signal.size_usd / signal.market_price if signal.market_price > 0 else 0,
                cost_usd=signal.size_usd,
                market_title=market.title,
                bucket_label=signal.bucket_label,
                strategy='confident',
                city=city,
                slug=market.slug,
                resolution_time=market.resolution_time,
            )
            if pos:
                self.trades_placed += 1
                self.telegram.notify_trade(
                    'BUY', signal.bucket_label, signal.market_price,
                    signal.size_usd, pos.shares, 'confident',
                    edge=signal.edge, city=city,
                )

    def _check_resolutions(self):
        """Check if any positions resolved, redeem winners."""
        self.pm.check_resolutions()
        redeemed = self.pm.redeem_all_winning()
        if redeemed > 0:
            log.info(f"💰 Redeemed {redeemed} winning positions")
            self.telegram.send(f"💰 Redeemed {redeemed} winning positions!")

    def _print_dashboard(self):
        """Print comprehensive dashboard."""
        stats = self.pm.get_stats()
        open_pos = self.pm.get_open_positions()

        log.info(f"\n{'━'*60}")
        log.info(f"  🌤️  WEATHER SNIPER DASHBOARD")
        log.info(f"{'━'*60}")
        log.info(f"  Mode:        {stats['mode']}")
        log.info(f"  Balance:     ${stats['balance']:.2f}")
        log.info(f"  Portfolio:   ${stats['portfolio_value']:.2f}")
        log.info(f"  Total PnL:   ${stats['total_pnl']:+.2f} ({stats['roi_pct']:+.1f}%)")
        log.info(f"{'─'*60}")
        log.info(f"  Trades:      {stats['total_trades']}")
        log.info(f"  Win Rate:    {stats['win_rate']:.0f}% ({stats['wins']}W / {stats['losses']}L)")
        log.info(f"  Open:        {stats['open_positions']} positions")
        log.info(f"  Redeemed:    ${stats['total_redeemed']:.2f}")
        log.info(f"  Signals:     {self.signals_generated} generated")
        ml_status = self.ml.get_status()
        if ml_status['enabled']:
            log.info(f"  ML Engine:   {ml_status['model']} ({ml_status['tokens_used']} tokens)")
        log.info(f"  Contexts:    {stats.get('active_contexts', 0)} active markets")
        log.info(f"{'─'*60}")

        if open_pos:
            log.info(f"  OPEN POSITIONS:")
            for p in open_pos[:10]:
                pnl_e = '📈' if p.unrealized_pnl >= 0 else '📉'
                log.info(
                    f"    {pnl_e} {p.city:12} {p.bucket_label[:30]:30} "
                    f"${p.entry_price:.4f}→${p.current_price:.4f} "
                    f"({p.roi_pct:+.0f}%)"
                )

        log.info(f"{'━'*60}\n")

    def print_status(self):
        """Print status and exit."""
        Config.print_status()
        self._print_dashboard()

    def run_loop(self):
        """Main trading loop."""
        Config.print_status()
        log.info("🚀 Weather Sniper Bot starting...")
        log.info(f"   Scan interval: {Config.SCAN_INTERVAL_SECONDS}s")
        log.info(f"   Days ahead: {Config.SCAN_DAYS_AHEAD}")
        log.info(f"   Strategies: Sniper + {'Spread' if Config.SPREAD_ENABLED else '(OFF)'}")
        log.info(f"   Telegram: {'ON' if self.telegram.enabled else 'OFF'}")
        log.info("")

        # Start Telegram command polling
        self.telegram.start_polling()
        self.telegram.send("🚀 <b>Weather Sniper Bot started!</b>\nUse /help for commands.")

        try:
            while True:
                try:
                    self.run_once()
                except KeyboardInterrupt:
                    raise
                except Exception as e:
                    log.error(f"Scan error: {e}")

                log.info(f"⏳ Next scan in {Config.SCAN_INTERVAL_SECONDS}s...")
                time.sleep(Config.SCAN_INTERVAL_SECONDS)

        except KeyboardInterrupt:
            log.info("\n🛑 Bot stopped by user")
            self._print_dashboard()
            self.telegram.send("🛑 Bot stopped.")
            self.telegram.stop_polling()


def main():
    parser = argparse.ArgumentParser(description='Weather Sniper Bot')
    parser.add_argument('--live', action='store_true', help='Enable live trading')
    parser.add_argument('--paper', action='store_true', help='Paper/dry-run mode (default)')
    parser.add_argument('--once', action='store_true', help='Run single scan then exit')
    parser.add_argument('--status', action='store_true', help='Print status and exit')
    parser.add_argument('--balance', type=float, help='Override starting balance')
    parser.add_argument('--days', type=int, default=3, help='Days ahead to scan')
    args = parser.parse_args()

    if args.live:
        Config.TRADING_MODE = 'live'
    if args.balance:
        Config.STARTING_BALANCE = args.balance
    if args.days:
        Config.SCAN_DAYS_AHEAD = args.days

    bot = WeatherBot()

    if args.status:
        bot.print_status()
    elif args.once:
        bot.run_once()
        bot._print_dashboard()
    else:
        bot.run_loop()


if __name__ == '__main__':
    main()
