# Trade Setup Calculator

> **Status:** Web: Implemented | Mobile: N/A

## Overview

Calculates entry, stop-loss, take-profit levels, position sizing, and leverage for a given signal. Uses ATR-based stop-loss (adapts to current volatility) and fixed 1:1/1:2/1:3 risk-reward ratios. Only produces output for active BUY or SELL signals — returns null for WAIT.

## Database Schema

No persistent data. Computed on-demand from live exchange data. Settings (balance, risk%, max leverage) persisted to `data/settings.json`.

**Settings schema:**
```json
{
  "account_balance": 1000.0,
  "risk_pct": 0.02,
  "max_leverage": 5
}
```

Default values: `account_balance=1000.0`, `risk_pct=0.02` (2%), `max_leverage=5`.

## Business Logic

### Trigger Condition

`calculate_trade_setup()` returns `None` when `signal not in ("BUY", "SELL")` or `current_price` is `None` or `<= 0`.

### ATR-Based Stop Loss

```
1. Fetch 30 × 15M candles
2. Calculate ATR(14) via pandas_ta
3. sl_distance_abs = ATR[-1] * 1.5  (atr_multiplier = 1.5)
4. Fallback if ATR fetch fails: sl_distance_abs = entry * 0.015 (1.5%)
5. Clamp: max(entry * 0.005, min(sl_distance_abs, entry * 0.05))
   → SL always between 0.5% and 5% of entry price
```

### Stop-Loss Levels

```
LONG:  stop_loss = entry - sl_distance_abs
SHORT: stop_loss = entry + sl_distance_abs
```

### Take-Profit Levels (fixed R:R)

```
LONG:  tp1 = entry + sl_distance_abs  (1:1 R:R)
       tp2 = entry + sl_distance_abs * 2  (1:2 R:R)
       tp3 = entry + sl_distance_abs * 3  (1:3 R:R)
SHORT: tp1 = entry - sl_distance_abs
       tp2 = entry - sl_distance_abs * 2
       tp3 = entry - sl_distance_abs * 3
```

`tp1_pct`, `tp2_pct`, `tp3_pct` expressed as percentage of entry (e.g., `sl_pct * 100`, `sl_pct * 200`, `sl_pct * 300`).

### Position Sizing

```
sl_pct = sl_distance_abs / entry
risk_amount = account_balance * risk_pct
position_size_usdt = risk_amount / sl_pct
position_size_coin = position_size_usdt / entry
```

### Leverage

```
leverage = min(max(2, round(1 / sl_pct)), max_leverage)
```

Auto-calculated: tighter SL → higher leverage. Clamped to `[2, max_leverage]`.

### Input Validation (API layer)

- `balance`: clamped to `max(balance, 1.0)` — minimum $1
- `risk_pct`: clamped to `max(0.001, min(risk_pct, 0.10))` — 0.1% to 10%
- `max_leverage`: clamped to `max(1, min(max_lev, 20))` — 1x to 20x

## API Contract

### `GET /api/trade-setup?symbol=BTC/USDT&balance=1000&risk_pct=0.02&max_leverage=5`

Returns trade setup for the current signal on a symbol.

**Query params:**
- `symbol` — must be in `SYMBOLS` allowlist
- `balance` (float, optional) — account balance in USDT; defaults to saved settings value
- `risk_pct` (float, optional) — fraction of balance to risk; defaults to saved settings
- `max_leverage` (int, optional) — maximum allowed leverage; defaults to saved settings

**Response 200 (active signal):**
```json
{
  "symbol": "BTC/USDT",
  "direction": "LONG",
  "entry_price": 84321.5,
  "stop_loss": 82981.0,
  "sl_pct": 1.59,
  "tp1": 85662.0,
  "tp2": 87002.5,
  "tp3": 88343.0,
  "tp1_pct": 1.59,
  "tp2_pct": 3.18,
  "tp3_pct": 4.77,
  "rr1": 1.0,
  "rr2": 2.0,
  "rr3": 3.0,
  "leverage": 3,
  "risk_amount": 20.0,
  "position_size_usdt": 1258.0,
  "position_size_coin": 0.014919,
  "account_balance": 1000.0,
  "risk_pct": 0.02,
  "confidence_score": 72.5,
  "confidence_label": "Medium",
  "timestamp": "2026-03-19 12:00:00"
}
```

**Response 200 (no active signal):** `null`
**Response 400:** `{"error": "Unknown symbol"}` or `{"error": "Invalid parameter value"}`

### `GET /api/settings`

Returns current settings.

**Response 200:**
```json
{
  "account_balance": 1000.0,
  "risk_pct": 0.02,
  "max_leverage": 5
}
```

### `POST /api/settings`

Save updated settings.

**Request body:** Same shape as GET response.
**Response 200:** `{"status": "ok", "settings": {...}}`
**Response 400:** `{"error": "Invalid JSON"}` or `{"error": "Invalid settings data"}`

## Permissions & Access Control

No authentication. Local tool only. Settings are stored per-machine in `data/settings.json`.

## Edge Cases

| Condition | Behavior |
|-----------|----------|
| Signal is WAIT | Returns `null` — no setup possible |
| `current_price` is None | Returns `null` |
| ATR fetch fails or < 15 rows | Falls back to 1.5% of entry as SL distance |
| ATR value = 0 | ATR branch skipped, fallback used |
| SL distance < 0.5% of entry | Clamped up to 0.5% |
| SL distance > 5% of entry | Clamped down to 5% |
| Calculated leverage < 2 | Clamped to 2 (minimum leverage) |
| Calculated leverage > max_leverage | Clamped to max_leverage |
| `sl_pct = 0` (entry = 0) | `position_size_usdt = 0` — guarded by `entry > 0` check |

## Error States

| Error | HTTP | Message |
|-------|------|---------|
| Unknown symbol | 400 | `{"error": "Unknown symbol"}` |
| Non-numeric balance/risk_pct/max_leverage | 400 | `{"error": "Invalid parameter value"}` |
| Invalid JSON on POST /api/settings | 400 | `{"error": "Invalid JSON"}` |
| Invalid settings data | 400 | `{"error": "Invalid settings data"}` |

## UI/UX Behavior

### Web

- **Trade Setup card**: appears below signal card when `signal = BUY or SELL`. Shows entry, SL, TP1/TP2/TP3 with percentage distances, position size in USDT and coin, leverage, risk amount.
- **Settings panel**: inputs for account balance, risk %, max leverage. Saved to server on submit. Values persist across page refreshes.
- **Save Trade button**: pre-fills trade journal form with all calculated values — one click to log the trade.
- **ATR indicator**: setup card shows current ATR value used for SL calculation. If ATR unavailable, shows "1.5% fallback" label.
- **R:R labels**: each TP level shows its risk-reward ratio (1:1, 1:2, 1:3).

### Mobile

N/A

## Platform Notes

- Trade setup is computed fresh on each API call (no caching) since it depends on both signal data (cached 60s) and live ATR (refetched from exchange).
- Confidence score and label are passed through from the analysis result — the trade setup card shows them alongside the levels.

## Related Docs

- `analyzer.py:403` — `calculate_trade_setup()`
- `analyzer.py:420` — ATR-based SL calculation
- `app.py:2548` — `GET /api/trade-setup`
- `app.py:2570` — `GET /api/settings`
- `app.py:2575` — `POST /api/settings`
- `app.py:22` — `DEFAULT_SETTINGS`
