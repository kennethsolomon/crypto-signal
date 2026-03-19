# Findings — 2026-03-19 — Crypto Signal Dashboard Improvements for ByBit

## Problem Statement
User trades futures on ByBit (beginner leverage) and wants a dashboard that:
- Shows live market signals with alerts when a trade is forming
- Provides copy-paste ready trade setups (entry, SL, TP, leverage, position size)
- Tracks trade history (manual entry logging)
- Includes a built-in trading guide
- Requires minimal daily time commitment (check once or twice, act on alerts)

## Requirements
- **Platform:** ByBit perpetual futures (beginner leverage: 2x-5x max)
- **Style:** Daily trading, 1-2 high-quality setups per day
- **Risk model:** Fixed % risk per trade (2% default)
- **TP strategy:** Fixed % (TP1: 2%, TP2: 5%, TP3: 8%) — simple and predictable for beginners
- **Copy format:** Multi-line text with one-click copy to clipboard
- **Trade logging:** Manual entry logging for history/performance tracking
- **Guide:** Built-in trading guide explaining the framework and how to use signals

## Current State (from codebase exploration)

### Architecture
- **Backend:** Flask (app.py) with in-memory cache (60s TTL)
- **Frontend:** Vanilla JS embedded in Python string (DASHBOARD_HTML), no framework
- **Analyzer:** analyzer.py with 5-rule confluence (binary pass/fail, no confidence scoring)
- **Endpoints:** `/api/analyze`, `/api/history`, `/api/symbols`
- **Exchange:** ByBit (switched from Binance — user trades on ByBit)
- **Polling:** 60-second refresh cycle

### Signal Logic (5-Rule Confluence)
| Rule | Timeframe | Indicator | Logic |
|------|-----------|-----------|-------|
| 1. Trend Alignment | 4H | EMA 200 | Price above/below EMA200 |
| 2. RSI Momentum | 1H | RSI 14 | RSI 50-70 rising (long) / 30-50 falling (short) |
| 3. MACD Crossover | 1H | MACD 12/26/9 | Cross above/below signal in last 3 candles |
| 4. EMA Stack | 15M | EMA 9/21 | Price > EMA9 > EMA21 (long) / inverse (short) |
| 5. Volume Surge | 15M | Volume ratio | Current vol >= 1.2x 20-period avg |

### Gaps Identified
- No confidence scoring (all-or-nothing)
- No entry/SL/TP calculations
- No position sizing
- No trade logging
- No alerts (user must watch dashboard)
- No guide
- 60s polling feels sluggish
- Signal history is in-memory only (lost on restart)

## Chosen Approach: Hybrid (Approach C) — All 3 Phases

### Phase 1: Confidence Scoring + Real-Time UI
- Add weighted rule strength scoring (0.0–1.0 per rule)
  - Rule 1 (4H trend): 2.0x weight
  - Rules 2-3 (1H momentum): 1.5x weight each
  - Rules 4-5 (15M micro): 1.0x weight each
- Signal staging: Green (>=85%), Yellow (70-84%), Red (<70%)
- Upgrade polling to 10s for near-real-time feel
- Add "signal forming" alert when 3-4/5 rules pass

### Phase 2: Trade Setup Card + Copy Features
- Calculate entry price (current market price at signal)
- Stop Loss: ATR-based or recent swing low/high
- Take Profit levels: TP1 (2%), TP2 (5%), TP3 (8%)
- Position sizing: based on 2% risk of account balance (user-configurable)
- Recommended leverage: 2x-5x range based on confidence score
- Copy-to-clipboard: multi-line format for ByBit
- Built-in trading guide panel

### Phase 3: Trade Logging + History
- Manual trade entry form (symbol, direction, entry price, SL, TP, leverage, size)
- Track open/closed trades
- Calculate P&L per trade
- Win/loss rate, average R:R
- Persist to JSON file (simple, no DB needed)
- Dashboard stats panel

## Key Decisions
| Decision | Rationale |
|----------|-----------|
| Fixed % TP (2/5/8%) | Simple, predictable for beginners. No need for ATR complexity yet |
| 2% risk per trade | Standard risk management, protects account |
| 2x-5x leverage max | Beginner-safe, avoids liquidation risk |
| JSON file for persistence | No database dependency, easy to backup/inspect |
| 10s polling (not WebSocket) | Simpler implementation, sufficient for daily trading style |
| Confidence scoring | Transforms binary signals into quality-graded entries |
| Built-in guide | User learns the system without external docs |

## Copy-to-Clipboard Format (ByBit)
```
=== TRADE SETUP ===
Pair:      BTC/USDT
Direction: LONG
Entry:     $67,250.00
Stop Loss: $65,850.00 (-2.08%)
TP1:       $68,595.00 (+2.00%)
TP2:       $70,612.50 (+5.00%)
TP3:       $72,630.00 (+8.00%)
Leverage:  3x
Size:      0.015 BTC ($1,008.75)
Risk:      2% of balance
Confidence: 87% (Strong)
Signal:    2026-03-19 14:30 UTC
===================
```

## Open Questions
- None — user said "whatever you want, just build all of it"
