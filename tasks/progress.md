# Progress Log

## Session: 2026-03-19
- Started: 12:00
- Summary: Milestone 1 backend complete (Wave 0 + Wave 1)

## Work Log
- 2026-03-19 12:05 — Wave 0: Switched exchange Binance→ByBit (analyzer.py:14), updated header + settings text (app.py)
- 2026-03-19 12:08 — Task 1.1: Added strength scoring (0.0-1.0) to all 5 rules in analyzer.py
  - Rule 1: distance from EMA200 normalized by 2% of EMA value
  - Rule 2: distance from RSI range midpoint (60 for long, 40 for short)
  - Rule 3: freshness-based (1.0/0.66/0.33 based on crossover recency)
  - Rule 4: price-EMA21 spread normalized by 2% of EMA21
  - Rule 5: (ratio - 1.0) / 1.0, capped at 1.0
- 2026-03-19 12:08 — Task 1.2: Added weighted confidence score to analyze()
  - Weights: [2.0, 1.5, 1.5, 1.0, 1.0], total=7.0
  - Returns: confidence_score, confidence_label (Strong/Medium/Weak), confidence_color
- 2026-03-19 12:08 — Task 1.3: Added signal forming detection (forming=true when 3-4 rules pass)

## Test Results
| Command | Expected | Actual | Status |
|---------|----------|--------|--------|
| `python -c "from analyzer import analyze; r=analyze('BTC/USDT')"` | confidence_score, strength per rule, forming field | All fields present, BTC: 40.9% Weak, strengths: 0.937/0.09/0.66/0.224/0.193 | PASS |

- 2026-03-19 12:32 — Task 2.1: Added calculate_trade_setup() to analyzer.py
  - Swing low/high SL from 15M data (0.5%-5% range, 1.5% fallback)
  - TP levels: +2%, +5%, +8% from entry
  - Position sizing: (balance * risk%) / sl_distance
  - Leverage: min(max(2, round(1/sl_pct)), max_leverage)
  - R:R ratios for each TP level
- 2026-03-19 12:32 — Tasks 2.2+2.3: Added /api/trade-setup, /api/settings endpoints + data/settings.json persistence
- 2026-03-19 12:40 — Tasks 2.4-2.7: Frontend Wave 4 complete
  - Trade Setup Card with direction badge, entry/SL/TP/leverage/size/R:R
  - Copy Setup button (multi-line ByBit format, clipboard API)
  - Settings panel (balance, risk%, max leverage, auto-save with debounce)
  - Trading Guide (collapsible, 5 sections including ByBit step-by-step)

## Test Results (Milestone 2)
| Command | Expected | Actual | Status |
|---------|----------|--------|--------|
| `calculate_trade_setup(forced_buy)` | entry/SL/TP/leverage/size | All fields correct, BTC $84k, SL 5%, lev 5x | PASS |
| `GET /api/settings` | default settings | `{balance:1000, risk:0.02, max_lev:5}` | PASS |
| `POST /api/settings` | saves and returns | saved {balance:2000, risk:0.01} | PASS |
| All 13 UI elements present | FOUND | All FOUND in 38.9KB HTML | PASS |

## Error Log
| Timestamp | Error | Attempt | Resolution |
|-----------|-------|---------|------------|
| (none)    |       |         |            |

### 2026-03-19 Signal Rule Upgrade (Option B) — COMPLETED
- Branch: `feature/signal-rule-upgrade-state-based`
- Changes: Replaced 2 event-based rules with state-based (MACD Histogram, OBV Trend); added Rule 6 StochRSI; added funding rate hard block; changed signal threshold to 5/6; updated forming detection to 4+/6; updated all frontend rule rows, badges, and guide text
- Tests: 62 tests passing, 100% new-code coverage (8 edge-case tests added)
- Security: 6 findings resolved (timeframe allowlist, safe int parse, float/int try-except, financial param bounds, host 127.0.0.1)
- Review: simplify pre-pass extracted _stoch_rsi_error, _load_json, _save_json helpers; promoted RULE_WEIGHTS + SIGNAL_THRESHOLD to module level; fixed stale docstring
- E2E: All 13 acceptance criteria verified via Playwright MCP — funding badge, forming banner, 6-rule UI, X/6 language
- Files changed: analyzer.py, app.py, tests/test_analyzer.py, tasks/
