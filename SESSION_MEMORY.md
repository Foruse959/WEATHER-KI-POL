# Session Memory — Weather Sniper Bot

## Session 2 (May 29, 2026) — Full Build with Backtest Validation

### Reference Wallet Research (data-api.polymarket.com/positions)

**Wallet 1 (0x594e) — The Big Sniper:**
- $58,471 REALIZED PnL | 88 weather positions | 82 redeemable
- 91% entries < $0.10 | Avg entry: $0.087 | Max 13,082 shares
- Cities: Wellington(9), Ankara(6), Lucknow(6), Seoul(6), Tokyo(6)
- ACTIVELY TRADING TODAY (May 29, 2026) — 50 trades in last 24h
- Trades both "highest temp" and "lowest temp" markets
- Buys expensive ($0.96-0.99) when very confident (lock-in wins)

**Wallet 2 (0x331b) — US Weather Focus:**
- $154 invested | Mostly US cities (Seattle, NYC, Houston)
- Higher entry prices (avg $0.66) — more conservative
- Only 6 positions, small operation

**Wallet 3 (0x15ce) — Diversified:**
- $5,625 invested | 25 weather positions across NYC, Madrid, Lagos, Seoul, London
- Mix of cheap ($0.01-0.10) and mid ($0.10-0.50) entries
- Also trades non-weather (F1, FIFA World Cup)

### KEY FINDING: Market Slug Pattern
```
highest-temperature-in-{city}-on-{month}-{day}-{year}
lowest-temperature-in-{city}-on-{month}-{day}-{year}
```
Example: `highest-temperature-in-tokyo-on-may-29-2026`
- Each event has 11 markets (temperature buckets)
- Found 39+ LIVE markets on May 29, 2026
- Cities: houston, lucknow, seoul, tokyo, london, taipei, hong-kong, beijing, ankara

### Data API Fields
```
proxyWallet, asset, conditionId, size, avgPrice, initialValue, 
currentValue, cashPnl, percentPnl, totalBought, realizedPnl, 
percentRealizedPnl, curPrice, redeemable, mergeable, title, 
slug, icon, eventId, eventSlug, outcome, outcomeIndex, 
oppositeOutcome, oppositeAsset, endDate, negativeRisk
```

### Backtest Results (60 days, 6 cities)
- **$10 → $1,120 in 60 days (+11,107% ROI)**
- 364 trades | 25.8% win rate (94W / 270L)
- Even 25% WR is hugely profitable due to 7-20x payoff on wins
- Best cities: Ankara (35% WR), Tokyo (29%), Seoul/Taipei/London (23-24%)
- Strategy validated: multi-model ensemble beats lagging market prices

### Architecture (v1.1)
```
dashboard.py         Main loop + live dashboard
├── bot/
│   └── telegram_ui.py    Notifications + /status /positions /redeem commands
├── data/
│   ├── weather_fetcher.py     5 models (ECMWF, GFS, ICON, JMA, GEM) + OWM + weather.gov
│   ├── probability_engine.py  Ensemble → normal CDF → bucket probabilities
│   ├── market_scanner.py      Slug-based scanning (confirmed pattern)
│   └── clob_client.py         CLOB V2 orders (GTC limit)
├── strategies/
│   ├── sniper_strategy.py     Buy cheap mispriced buckets
│   └── spread_strategy.py     Multi-outcome spread
├── trading/
│   ├── executor.py            Legacy (being replaced)
│   └── position_manager.py    Full position lifecycle: track → update → resolve → redeem
├── backtest/
│   └── weather_backtest.py    Historical backtest with simulated forecast error
├── config.py                  Paper/live mode, all params
└── logger.py                  Structured logging
```

### What's Done
- [x] Multi-source weather fetching (Open-Meteo 5 models + OWM + weather.gov)
- [x] Probability engine (ensemble CDF)
- [x] Market scanner with CONFIRMED slug pattern (finds real live markets)
- [x] Sniper strategy (buy cheap + edge filter)
- [x] Spread strategy (multi-outcome adjacent buckets)
- [x] Position manager (track, update prices, resolve, redeem)
- [x] Balance tracking (paper + on-chain)
- [x] Telegram bot (notifications + commands: /status /positions /markets /redeem /help)
- [x] Dashboard with live stats display
- [x] Backtest validated ($10→$1120 in 60 days)
- [x] Reference wallet research (3 wallets analyzed)
- [x] Paper/dry-run mode (default, safe)
- [x] Railway deployment ready (Procfile + railway.toml)

### Next Session Should
1. Run live paper test on today's markets (validate market scanner finds real opportunities)
2. Connect CLOB for live order placement (GTC limit orders)
3. Add "copy-trading" mode — mirror Wallet1's trades in real-time
4. Add resolution time tracking (Tokyo high resolves ~14:00 UTC next day)
5. Add auto-sell logic (sell at profit if price rises before resolution)
6. Tune parameters: maybe lower min_edge to 5% for more trades
7. Add Binance weather index cross-check (if available)
8. Track reference wallet trades in real-time for signal intelligence
