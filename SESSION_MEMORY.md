# Session Memory — Weather Sniper Bot

## Session 1 (May 29, 2026) — Initial Build

### What Was Built
- Complete weather trading bot for Polymarket weather markets
- Multi-source forecast fetching (Open-Meteo 5 models, OpenWeatherMap, weather.gov)
- Probability engine (ensemble normal-distribution CDF over temperature buckets)
- Market scanner (Gamma API search for weather/temperature markets)
- Two strategies: **Sniper** (cheap mispriced buckets) + **Multi-Outcome Spread**
- Trading executor with **paper/dry-run mode** and live CLOB integration
- Main dashboard loop with logging and stats

### Architecture
```
dashboard.py  →  MarketScanner (find weather markets)
              →  WeatherFetcher (multi-model forecasts)
              →  ProbabilityEngine (ensemble → bucket probabilities)
              →  SniperStrategy + SpreadStrategy (signal generation)
              →  TradingExecutor (paper or live orders)
```

### Key Decisions
- Paper mode is DEFAULT (safe for testing)
- CLOB auth reused from polymarket-bot-v2 (sig_type=3, V2 account)
- Open-Meteo gives 5 free models (ECMWF, GFS, ICON, JMA, GEM)
- Kelly criterion for sizing (conservative 0.15 fraction)
- Sniper: buy buckets priced < $0.15 when our P > market + 10% edge
- Spread: buy primary + neighbors with 0.4 decay

### Next Session Should
- Test with real Polymarket weather markets (run `python dashboard.py --once`)
- Tune edge thresholds based on actual market prices seen
- Add historical backtest using resolved weather markets
- Add Telegram notifications
- Consider adding more weather models (HRRR for US, AROME for Europe)
- Add auto-resolution checking (poll market status, mark positions won/lost)
