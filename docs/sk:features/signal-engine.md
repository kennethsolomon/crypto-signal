# Signal Engine

> **Status:** Web: Implemented | Mobile: N/A

## Overview

6-rule confluence framework for crypto futures day trading on ByBit. A directional signal (BUY/SELL) fires only when 5 out of 6 independent technical rules agree on direction. One miss is allowed to account for real-market conditions where all rules rarely align simultaneously.

## Database Schema

No persistent schema. Analysis results are cached in memory (`cache` dict in `app.py`) with a 60-second TTL. Signal history is persisted to `data/signals.json` (flat JSON array) when a new signal state is detected.

Signal history record shape:
```json
{
  "symbol": "BTC/USDT",
  "signal": "BUY | SELL | WAIT",
  "forming": true,
  "long_rules_met": 5,
  "short_rules_met": 1,
  "total_rules": 6,
  "confidence_score": 72.5,
  "confidence_label": "Medium",
  "timestamp_display": "2026-03-19 12:00:00"
}
```

## Business Logic

### Symbols

Tracked: `["BTC/USDT", "ETH/USDT", "SOL/USDT", "BNB/USDT", "XRP/USDT", "DOGE/USDT"]` — ByBit spot symbols, converted to perpetual format (`/USDT:USDT`) only for funding rate fetch.

### The 6 Rules

| # | Name | Timeframe | Logic |
|---|------|-----------|-------|
| 1 | Trend Alignment (4H EMA 200) | 4H | Price above EMA200 = LONG; below = SHORT |
| 2 | RSI Momentum (1H) | 1H | RSI(14) 50–70 = LONG; 30–50 = SHORT |
| 3 | MACD Histogram (1H) | 1H | Histogram positive & growing last 3 candles = LONG; negative & falling = SHORT |
| 4 | EMA Stack (15M) | 15M | Price > EMA9 > EMA21 = LONG; Price < EMA9 < EMA21 = SHORT |
| 5 | OBV Trend (15M) | 15M | OBV linear slope over 5 candles positive = LONG; negative = SHORT |
| 6 | Stochastic RSI (1H) | 1H | K < 50 crossing up over D = LONG; K > 50 crossing down below D = SHORT |

### Rule Weights

`RULE_WEIGHTS = [2.0, 1.5, 1.5, 1.0, 1.0, 1.0]` — total weight 8.0. Used for confidence score only; signal decision uses raw count.

### Signal Decision

```
if long_count >= 5 and long_count > short_count → BUY
if short_count >= 5 and short_count > long_count → SELL
if both >= 5 (tie) → WAIT
else → WAIT
```

`SIGNAL_THRESHOLD = 5`

### Forming State

`forming = True` when `4 <= long_count <= 5` or `4 <= short_count <= 5` but no signal fires. Shown as a banner warning the user a signal may be imminent.

### Funding Rate Hard Block

`fetch_funding_rate()` calls `exchange.fetch_funding_rate(perp_symbol)` (ccxt, ByBit public endpoint). `FUNDING_EXTREME_THRESHOLD = 0.0005` (0.05%).
- Rate >= +0.05% → blocks BUY signal → WAIT + `signal_blocked_reason = "Extreme positive funding — long squeeze risk"`
- Rate <= -0.05% → blocks SELL signal → WAIT + `signal_blocked_reason = "Extreme negative funding — short squeeze risk"`
- On fetch failure → `rate = None`, no block (neutral)

### Confidence Score

```
long_confidence = sum(strength * weight for passing long rules) / 8.0 * 100
short_confidence = sum(strength * weight for passing short rules) / 8.0 * 100
confidence_score = max(long_confidence, short_confidence)
```

Labels: `Strong` (≥ 85%), `Medium` (≥ 70%), `Weak` (< 70%).

### Strength per Rule

- Rule 1: `abs(price - ema200) / (ema200 * 0.02)` capped at 1.0
- Rule 2: distance from RSI midpoint (60 for long, 40 for short), divided by 20, capped at 1.0
- Rule 3: `abs(histogram[-1]) / (price * 0.001)` capped at 1.0
- Rule 4: `abs(price - ema21) / (ema21 * 0.02)` capped at 1.0
- Rule 5: `abs(slope) / avg_volume` capped at 1.0
- Rule 6: `(50 - K) / 50` for LONG; `(K - 50) / 50` for SHORT, capped at 1.0

### Caching

Results cached per symbol for 60 seconds (`CACHE_TTL = 60`). Fresh analysis fetched on cache miss or after TTL. Cache uses `threading.Lock` for concurrent request safety.

## API Contract

### `GET /api/analyze?symbol=BTC/USDT`

Returns current analysis for one symbol.

**Query params:**
- `symbol` (string, required) — must be in `SYMBOLS` allowlist

**Response 200:**
```json
{
  "symbol": "BTC/USDT",
  "signal": "BUY | SELL | WAIT",
  "signal_color": "green | red | gray",
  "forming": false,
  "long_rules_met": 5,
  "short_rules_met": 1,
  "total_rules": 6,
  "funding_rate": -3.4e-06,
  "funding_blocked": null,
  "signal_blocked_reason": null,
  "confidence_score": 72.5,
  "confidence_label": "Medium",
  "confidence_color": "orange",
  "current_price": 84321.5,
  "timestamp_display": "2026-03-19 12:00:00",
  "rules": [
    {
      "rule": "Trend Alignment (4H EMA 200)",
      "long": true,
      "short": false,
      "strength": 0.93,
      "value": "Price 84321.5 vs EMA200 80102.3",
      "signal_hint": "LONG: price above EMA200 | SHORT: price below EMA200",
      "error": false,
      "description": "Macro trend direction"
    }
  ]
}
```

**Response 400:** `{"error": "Unknown symbol"}`

### `GET /api/history`

Returns all saved signal history (flat array from `data/signals.json`).

### `GET /api/symbols`

Returns `["BTC/USDT", "ETH/USDT", "SOL/USDT", "BNB/USDT", "XRP/USDT", "DOGE/USDT"]`.

### `GET /api/chart-data?symbol=BTC/USDT&timeframe=15m&limit=100`

Returns OHLCV candles + EMA9/EMA21 overlay data for charting.

**Query params:**
- `symbol` — must be in `SYMBOLS` allowlist
- `timeframe` — must be in `ALLOWED_TIMEFRAMES = {"1m","5m","15m","1h","4h","1d"}`
- `limit` — integer 1–300, default 100

**Response 200:**
```json
{
  "candles": [{"time": 1710849600, "open": 83000, "high": 84500, "low": 82800, "close": 84321}],
  "ema9": [{"time": 1710849600, "value": 84100}],
  "ema21": [{"time": 1710849600, "value": 83800}]
}
```

**Response 400:** `{"error": "Unknown symbol"}` or `{"error": "Invalid timeframe"}`
**Response 500:** `{"error": "Chart data unavailable"}` — returned when `len(df) < 25`

## Permissions & Access Control

No authentication. Local tool only — server binds to `127.0.0.1:5001`. All endpoints are read-only analysis; no user-supplied data affects the signal engine.

## Edge Cases

| Condition | Behavior |
|-----------|----------|
| ByBit API down / symbol unsupported | Rule returns `error: True`, `long: False`, `short: False` — treated as failing rule |
| Insufficient candle data (`len(df) < min_required`) | Same as above per rule |
| Both long and short reach 5/6 simultaneously | Signal = WAIT (tie resolution) |
| Funding rate fetch fails | `rate: None`, `funding_blocked: None` — no block applied |
| OBV flat (slope = 0) | Rule returns `long: False`, `short: False`, `strength: 0.0` |
| StochRSI missing expected columns | Returns error dict via `_stoch_rsi_error()` |
| StochRSI fewer than 2 valid rows after dropna | Returns error dict |
| `analyze()` called concurrently for same symbol | Cache lock ensures only one fetch runs; second caller waits |

## Error States

| Error | HTTP | Message |
|-------|------|---------|
| Unknown symbol in `/api/analyze` | 400 | `{"error": "Unknown symbol"}` |
| Unknown timeframe in `/api/chart-data` | 400 | `{"error": "Invalid timeframe"}` |
| chart data unavailable (< 25 rows) | 500 | `{"error": "Chart data unavailable"}` |

## UI/UX Behavior

### Web

- **Symbol tabs**: 6 tabs at top of dashboard — one per symbol. Each shows `SYMBOL_TICKER` and current signal (`BUY / SELL / WAIT`) as a colored badge.
- **Signal card**: shows current signal direction, confidence score+label, funding rate badge, rules panel.
- **Rules panel**: 6 rows, one per rule. Each shows: rule name, LONG/SHORT pass indicators, strength bar (0–100%), description, signal_hint.
- **Forming banner**: shown when `forming = true` — "SYMBOL: DIRECTION signal forming — N/6 rules passing". Pulsing animation.
- **Funding rate badge**: color-coded — green (neutral), yellow (approaching threshold > 0.03%), red+BLOCKED (extreme). Shows "Funding: +0.012%" format.
- **Signal blocking banner**: shown when `signal_blocked_reason` is set — "⚠ Long blocked — extreme funding rate (+0.05%)" in red.
- **Auto-refresh**: 60-second polling cycle with countdown timer. 10-second "realtime" mode toggle available.
- **Browser notifications**: fires on new BUY/SELL signal per symbol (deduped — only fires once per state change).

### Mobile

N/A

## Platform Notes

- Single-file Flask app — all HTML/CSS/JS is embedded in `app.py` as `DASHBOARD_HTML` (large template string rendered via `render_template_string`).
- Exchange: ByBit via ccxt (public endpoints only — no API key required).
- Rate limiting: ccxt `enableRateLimit: True` — respects ByBit's rate limits automatically.

## Related Docs

- `analyzer.py` — all rule functions, `fetch_funding_rate()`, `analyze()`
- `app.py:2501` — `/` route (dashboard)
- `app.py:2506` — `/api/analyze`
- `app.py:2519` — `/api/history`
- `app.py:2524` — `/api/symbols`
- `app.py:2532` — `/api/chart-data`
- `tests/test_analyzer.py` — 62 tests covering all rules and edge cases
