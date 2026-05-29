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
