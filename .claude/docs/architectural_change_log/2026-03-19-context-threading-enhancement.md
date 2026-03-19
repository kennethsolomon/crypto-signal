# 6-Rule State-Based Signal Engine (March 19, 2026)

## Summary

Replaced two event-based rules (MACD Crossover, Volume Surge) with state-based equivalents. Added a sixth rule (Stochastic RSI) and a funding rate hard-block filter. Changed signal threshold from 5/5 to 5/6 (one miss allowed).

## Type of Architectural Change

**Feature / Rule Engine Extension**

## What Changed

**analyzer.py — Rule Engine:**
- `check_rule_3_macd()`: MACD Crossover → MACD Histogram State (histogram positive+growing for LONG, negative+falling for SHORT)
- `check_rule_5_volume()`: Volume Surge → OBV Trend (linear slope of On Balance Volume over 5 candles)
- New `check_rule_6_stoch_rsi()`: Stochastic RSI (1H) entry timing; uses `pandas_ta.stochrsi()`, returns K/D crossover direction
- New `fetch_funding_rate()`: calls ByBit perpetual funding rate endpoint; returns rate + blocked side when extreme (>0.05%)
- New `_stoch_rsi_error()` helper to eliminate 4x repeated early-return pattern
- `RULE_WEIGHTS` promoted to module-level (`[2.0, 1.5, 1.5, 1.0, 1.0, 1.0]`, total weight 8.0)
- `SIGNAL_THRESHOLD` and `FUNDING_EXTREME_THRESHOLD` promoted to module-level constants
- `analyze()` signal logic: `all(rules)` → `count >= 5`; conflict resolution: higher count wins, tie → WAIT
- Forming threshold: `>= 3` rules → `>= 4` rules

**app.py — API Hardening:**
- `ALLOWED_TIMEFRAMES` set for `/api/chart-data`
- Bounds clamping for `balance`, `risk_pct`, `max_leverage`
- `try/except (ValueError, TypeError)` on all float/int casts in trade endpoints
- `_load_json()` / `_save_json()` helpers replace 4x duplicated open/json patterns
- Server bind: `0.0.0.0` → `127.0.0.1`

**Statistics:**
- Lines added: ~1348 | Lines removed: ~340
- Files modified: analyzer.py, app.py, tests/test_analyzer.py

## Before & After

**Before:**
- 5 rules, all must pass (5/5) for a signal
- Rules 3 and 5 were event-based: rarely coincided with state-based rules in real markets
- Signal fired infrequently; system was effectively always WAIT
- Forming detected at 3+ rules

**After:**
- 6 rules, 5/6 must pass (one miss allowed)
- Rules 3 and 5 are state-based: persist while momentum/OBV trend holds
- Rule 6 (StochRSI) adds entry timing layer — filters premature entries
- Funding rate blocks signal when extreme — prevents squeeze traps
- Forming detected at 4+ rules (higher signal-to-noise)
- Confidence score weight total: 8.0 (was 7.0)

## Affected Components

- `analyzer.py` — core rule engine and `analyze()` function
- `app.py` — dashboard HTML, JS render logic, all API endpoints
- `tests/test_analyzer.py` — 62 tests covering all 6 rules + edge cases

## Migration/Compatibility

- No schema changes — all data is stored as JSON files
- No API surface changes — existing endpoints return same structure with added fields (`funding_rate`, `funding_blocked`, `signal_blocked_reason`)
- Dashboard UI is backwards-compatible — existing saved signals/trades unaffected
- `total_rules` field changes from 5 to 6 — any consumer relying on this value should be updated

## Verification

- [x] All affected code paths tested (62 tests, 100% new-code coverage)
- [x] Related documentation updated (CHANGELOG.md, trading guide in dashboard)
- [x] No breaking changes (added fields only; `total_rules` 5→6 noted above)
- [x] Dependent systems verified (E2E: all 13 acceptance criteria passed)
