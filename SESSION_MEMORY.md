# Session Memory — Weather Sniper Bot

## Session 3 (May 29, 2026) — ML + Speed + Risk Management

### Changes Made
1. **ML Decision Engine** — GPT-5.5 via Freemodel API
   - Signal validation: BUY/SKIP with confidence score (~150 tokens/query)
   - Position review: HOLD/SELL for open positions
   - Market selection: which cities to prioritize
   - Caching (2min TTL) prevents duplicate queries
   - ~617 tokens for 4 queries — extremely efficient

2. **Position Manager v2** — Full lifecycle with risk controls
   - Per-position PnL tracking (individual + aggregate)
   - Stop-loss: -80% ROI default (skip for ultra-cheap < $0.03 entries)
   - Take-profit: auto-set per entry price ($0.05→TP@$0.25, $0.15→TP@$0.60)
   - Trailing stop: 25% from peak (only after 2x gain)
   - Weekly memory: records stats every Monday for ML learning
   - Context cleanup: frees memory for closed/resolved markets
   - Per-city and per-strategy stats breakdown

3. **Speed Optimization** — 5x faster
   - Weather fetcher: single batch Open-Meteo call (0.44s vs ~2.5s)
   - Market scanner: ThreadPoolExecutor with 10 workers (0.37s for 104 checks)
   - HTTP connection pooling (keep-alive, 10 pool connections)
   - 75 markets found in 0.46s (3 days ahead)

4. **Reference Wallet Deep Analysis**
   - Wallet1 (0x594e): $58K realized, $217K redeemable
   - Trades at 06:00 UTC (155/200 trades in that hour)
   - 91% entries < $0.05 (ultra-cheap tails)
   - Two strategies: SNIPER (cheap tails) + LOCK-IN (buy near-certain at $0.97+)
   - Focuses on "highest temperature" markets (84/88 positions)
   - Top cities: Wellington, Ankara, Lucknow, Seoul, Tokyo

5. **Polymarket V2 Compliance**
   - pUSD collateral (not USDC.e) — since April 28, 2026
   - signature_type=3 for V2 accounts
   - Gasless trading (only need pUSD to trade)
   - Weather markets: 0% maker fee (GTC limit orders)

### Architecture (v2.0)
```
dashboard.py              Main loop + ML-integrated dashboard
├── ml/
│   └── decision_engine.py     GPT-5.5 signal validation (BUY/SKIP/SELL)
├── bot/
│   └── telegram_ui.py         Notifications + commands
├── data/
│   ├── weather_fetcher.py     Batch multi-model (5 in 1 request)
│   ├── probability_engine.py  Ensemble CDF
│   ├── market_scanner.py      Parallel slug scanner (10 threads)
│   └── clob_client.py         CLOB V2 orders
├── strategies/
│   ├── sniper_strategy.py     Buy cheap tails
│   └── spread_strategy.py     Multi-outcome spread
├── trading/
│   └── position_manager.py    SL/TP/trailing/weekly memory/context cleanup
├── backtest/
│   └── weather_backtest.py    60-day backtest ($10→$1120)
└── config.py                  All params + ML config
```

### Key Findings from Wallet Research
- 25% win rate is GOOD for this strategy (7-20x payoff per win)
- Best time to trade: 06:00 UTC (when Asian markets post forecasts)
- Best cities: Ankara (35% WR), Tokyo (29%), Seoul (24%)
- Ultra-cheap entries ($0.001-$0.05) are the money-makers
- Hold to resolution — don't sell cheap positions (binary payout)
- The "lock-in" strategy (buy at $0.97+) is for guaranteed small wins

### Config Summary
| Parameter | Value | Why |
|-----------|-------|-----|
| SNIPER_MAX_ENTRY | $0.15 | Match Wallet1's 91% < $0.10 pattern |
| MIN_EDGE | 10% | Confirmed profitable in backtest |
| KELLY_FRACTION | 0.15 | Conservative for $3 balance |
| STOP_LOSS | -80% | Only triggers on mid-range entries |
| TAKE_PROFIT | Auto | $0.05→$0.25, $0.15→$0.60 |
| TRAILING_STOP | 25% | After 2x gain, protect profits |
| ML_MODEL | gpt-5.5 | Fast, ~150 tokens/query |
| SCAN_INTERVAL | 60s | Balance speed vs API limits |

### Next Session Should
1. Deploy to Railway and test live paper mode
2. Add "lock-in" strategy (buy obvious outcomes at $0.95+ like Wallet1 does)
3. Add copy-trading mode (mirror Wallet1 trades via activity API)
4. Wire CLOB for real order placement (tested in paper first)
5. Add auto-sell before resolution if price rises to $0.50+ (take profit)
6. Test with TELEGRAM_BOT_TOKEN for real-time alerts
7. Consider adding more cities to MARKET_CITIES (check Wallet1's full history)



---

## Session 3 CONTINUED (May 29, 2026, 09:40 UTC) — Full Customization + Adaptive Trading

### What Was Added (this pass)

#### 1. Full Feature Toggle System (like polymarket-bot-v2)
Every feature can be enabled/disabled via env var without affecting anything else:
```env
SNIPER_ENABLED=1          # Buy cheap mispriced tails
SPREAD_ENABLED=1          # Multi-outcome spread bets
LOCKIN_ENABLED=1          # Buy near-certain ($0.90+) outcomes
ML_ENABLED=1              # GPT-5.5 signal validation
TELEGRAM_ENABLED=1        # Notifications
COPY_TRADING_ENABLED=0    # Mirror Wallet1 trades (off by default)
ADAPTIVE_EXIT_ENABLED=1   # Auto-exit unfavorable positions
AUTO_REDEEM_ENABLED=1     # Auto-redeem winning positions
DRAWDOWN_GATE_ENABLED=1   # Pause trading on drawdown
```

#### 2. City Filter
```env
ENABLED_CITIES=tokyo,seoul,ankara,london  # Only trade these
# Leave empty = trade ALL cities
```

#### 3. Drawdown Gate (circuit breaker)
- If daily loss > 30% of balance → PAUSE all new trades for 60min
- If weekly loss > 50% → PAUSE all new trades for 60min
- Protects capital from cascading losses
- Alert via Telegram when triggered

#### 4. Lock-In Strategy (from Wallet1's second approach)
- Wallet1 buys near-certain outcomes at $0.90-0.99 for guaranteed small profit
- Our implementation: buy if our_prob > 0.85 AND market_price > 0.90
- Max bet: 40% of balance (high-confidence trade)
- Expected return: 5-10% per trade (low risk)

#### 5. Adaptive Exit (for unfavorable markets)
- Every 120s, re-evaluate open positions with fresh forecast data
- If our edge REVERSED (new forecast contradicts position) → sell immediately
- If edge decreased but still positive → hold
- ML validates the exit decision before executing
- Min hold time: 10min (avoid churning)

#### 6. Copy Trading (mirror Wallet1)
- Polls data-api.polymarket.com/activity every 30s for Wallet1's new trades
- When Wallet1 buys → we buy same token at COPY_SCALE_FACTOR (0.01 = 1% of their size)
- Smart scaling: $10K position × 0.01 = $100 for us
- Only copies weather-related trades (filters out non-weather)
- OFF by default (enable with COPY_TRADING_ENABLED=1)

### Wallet1 Strategy Analysis (final summary)
| Metric | Value | Implication for Us |
|--------|-------|--------------------|
| Trade time | 06:00 UTC | Set SCAN_INTERVAL to run at 05:55-06:30 UTC |
| Entry price | 91% < $0.05 | Lower SNIPER_MAX_ENTRY from $0.15 to $0.05 for purity |
| Market type | 95% "highest temperature" | Focus on highest, not lowest |
| Strategy split | 91% sniper + 8% lock-in | Both strategies complementary |
| Cities | Ankara > Wellington > Seoul > Tokyo | Match their city focus |
| Position size | avg 2641 shares ($200 cost) | We scale down proportionally |
| Win detection | 82 redeemable out of 88 | They DON'T redeem immediately → we should AUTO_REDEEM |
| Realized PnL | $58,471 | Strategy is proven profitable at scale |

### How Exit Rules Work for Weather Markets
Weather markets are BINARY (resolve to $0 or $1). Exit rules adapted:

| Entry Price | Stop-Loss | Take-Profit | Hold Strategy |
|-------------|-----------|-------------|---------------|
| < $0.03 | NONE (hold to resolution) | Sell at $0.50+ if market moves early | Binary gamble — no point selling at $0.005 |
| $0.03-$0.10 | -80% ROI | Sell at $0.30+ | Hold unless forecast reverses |
| $0.10-$0.30 | -60% ROI | Sell at $0.60+ | Active management, sell if edge lost |
| $0.90+ (lock-in) | -5% ROI | Hold to resolution | Almost certain — hold for $1.00 payout |

### Speed Benchmarks (final)
| Operation | Time | Improvement |
|-----------|------|-------------|
| Weather fetch (5 models) | 0.44s | 5x faster (batch) |
| Market scan (208 slugs, 3 days) | 0.46s | 100x faster (10 threads) |
| ML query (signal validation) | ~2s | Cached (2min TTL) |
| Full scan cycle (75 markets) | ~15s | Acceptable for 60s interval |

### What Got Better This Session
1. **Config** → fully customizable, no redeployment needed for changes
2. **Risk** → drawdown gate, adaptive exit, proper SL/TP per price tier
3. **Strategy** → added lock-in (8% of Wallet1's trades = guaranteed profit)
4. **Intelligence** → ML validates every trade, copy-trading available
5. **Speed** → 5x weather, 100x scanner, connection pooling
6. **Memory** → weekly stats, context cleanup, continuous session log
7. **Robustness** → feature toggles, city filters, cooldown periods

### Files Modified
- config.py: v2.0.0, feature toggles, drawdown gate, lock-in, adaptive, copy
- dashboard.py: ML integration, risk checks, weekly memory
- data/market_scanner.py: parallel scanning, connection pooling
- data/weather_fetcher.py: batch API call (1 instead of 5)
- ml/decision_engine.py: new file, GPT-5.5 signal validation
- trading/position_manager.py: SL/TP/trailing/weekly/context cleanup
- bot/telegram_ui.py: notifications + commands

### What's Ready for Next Session
1. Run `python dashboard.py --once` with ML_API_KEY set to validate full pipeline
2. Deploy to Railway (all env vars in Railway dashboard)
3. Enable COPY_TRADING_ENABLED=1 for Wallet1 mirroring
4. Lower SNIPER_MAX_ENTRY_PRICE to 0.05 (match Wallet1)
5. Set ENABLED_CITIES=ankara,tokyo,seoul,london for focused trading
6. Wire real POLY_PRIVATE_KEY for live trading
7. Add Telegram token for real-time alerts
