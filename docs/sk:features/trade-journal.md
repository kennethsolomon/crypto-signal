# Trade Journal

> **Status:** Web: Implemented | Mobile: N/A

## Overview

Persistent trade log for tracking open and closed ByBit futures positions. Supports manual entry, closing with exit price, PnL calculation, and aggregate statistics (win rate, streaks, total PnL).

## Database Schema

No SQL database. Trades are stored as a flat JSON array in `data/trades.json`. Reads/writes are protected by `threading.Lock` (`trades_lock`).

**Trade record shape:**
```json
{
  "id": 1710849600000,
  "symbol": "BTC/USDT",
  "direction": "LONG | SHORT",
  "entry_price": 84321.5,
  "stop_loss": 82981.0,
  "tp1": 85662.0,
  "tp2": 87002.5,
  "tp3": 88343.0,
  "leverage": 3,
  "position_size_usdt": 1500.0,
  "position_size_coin": 0.017794,
  "risk_pct": 0.02,
  "risk_amount": 20.0,
  "confidence_score": 72.5,
  "status": "open | closed",
  "exit_price": null,
  "exit_reason": null,
  "pnl_usdt": null,
  "pnl_pct": null,
  "opened_at": "2026-03-19 12:00:00 UTC",
  "closed_at": null,
  "notes": ""
}
```

`id` = millisecond Unix timestamp at creation time (`int(time.time() * 1000)`).

## Business Logic

### PnL Calculation (on close)

```
LONG:  pnl_pct = (exit_price - entry_price) / entry_price * 100
SHORT: pnl_pct = (entry_price - exit_price) / entry_price * 100
pnl_usdt = position_size_usdt * (pnl_pct / 100)
```

Both values rounded to 2 decimal places.

### Stats Calculation (`/api/trades/stats`)

Computed from closed trades only:
- `win_rate`: `len(wins) / len(closed) * 100` — a win is `pnl_usdt > 0`
- `avg_rr`: average of `pnl_pct` across all closed trades
- `total_pnl_usdt` / `total_pnl_pct`: sum of all closed PnL values
- `best_trade_pnl` / `worst_trade_pnl`: max/min of `pnl_usdt`
- `win_streak` / `loss_streak`: max consecutive wins/losses (reverse chronological — most recent trade first)

### Ordering

New trades are inserted at index 0 (`trades.insert(0, trade)`) — most recent first.

## API Contract

### `GET /api/trades?status=all|open|closed`

Returns trade list filtered by status. Default `all`.

**Response 200:** JSON array of trade objects.

### `POST /api/trades`

Create a new open trade.

**Request body:**
```json
{
  "symbol": "BTC/USDT",
  "direction": "LONG",
  "entry_price": 84321.5,
  "stop_loss": 82981.0,
  "tp1": 85662.0,
  "tp2": 87002.5,
  "tp3": 88343.0,
  "leverage": 3,
  "position_size_usdt": 1500.0,
  "position_size_coin": 0.017794,
  "risk_pct": 0.02,
  "risk_amount": 20.0,
  "confidence_score": 72.5,
  "notes": ""
}
```

All numeric fields validated — returns 400 on non-numeric values. `status` is always set to `"open"` server-side.

**Response 201:** Full trade object.
**Response 400:** `{"error": "Invalid JSON"}` or `{"error": "Invalid trade data"}`

### `PUT /api/trades/<id>`

Update an open trade (close it or edit notes).

**Request body (close):**
```json
{
  "exit_price": 85500.0,
  "exit_reason": "tp1 | tp2 | tp3 | sl | manual"
}
```

**Request body (notes only):**
```json
{ "notes": "Closed at TP1, market reversed" }
```

If `exit_price` is provided: trade status → `"closed"`, PnL computed, `closed_at` set.

**Response 200:** Updated trade object.
**Response 400:** `{"error": "Invalid JSON"}` or `{"error": "Invalid exit_price"}`
**Response 404:** `{"error": "Trade not found"}`

### `GET /api/trades/stats`

Returns aggregate statistics across all trades.

**Response 200:**
```json
{
  "total_trades": 12,
  "open_trades": 2,
  "closed_trades": 10,
  "win_rate": 60.0,
  "avg_rr": 1.4,
  "total_pnl_usdt": 142.50,
  "total_pnl_pct": 14.25,
  "best_trade_pnl": 45.20,
  "worst_trade_pnl": -18.50,
  "win_streak": 3,
  "loss_streak": 2
}
```

When no closed trades exist, all numeric fields return 0.

## Permissions & Access Control

No authentication. Local tool only. All trades are stored locally — no user/account isolation needed.

## Edge Cases

| Condition | Behavior |
|-----------|----------|
| `exit_price` field present but `null` | Treated as no-close; only `notes` updated |
| `pnl_usdt` or `pnl_pct` is `null` on closed trade | Treated as 0 in stats calculations |
| `data/trades.json` missing or corrupt | `load_trades()` returns `[]` — empty journal |
| Concurrent create/close requests | `trades_lock` serializes all reads+writes |
| Trade ID not found on PUT | 404 returned |
| Non-numeric `exit_price` | 400 `{"error": "Invalid exit_price"}` |
| Non-numeric fields in POST body | 400 `{"error": "Invalid trade data"}` |

## Error States

| Error | HTTP | Message |
|-------|------|---------|
| Malformed JSON body | 400 | `{"error": "Invalid JSON"}` |
| Non-numeric numeric field on create | 400 | `{"error": "Invalid trade data"}` |
| Non-numeric exit_price on close | 400 | `{"error": "Invalid exit_price"}` |
| Trade not found on PUT | 404 | `{"error": "Trade not found"}` |

## UI/UX Behavior

### Web

- **Journal tab**: shows table of all trades with columns: symbol, direction, entry, SL, TP1/2/3, leverage, size, confidence, status, PnL, opened_at, notes, actions.
- **Open trades**: show "Close" button — opens modal to enter exit price and exit reason.
- **Closed trades**: show PnL in green (positive) or red (negative).
- **Stats bar**: win rate, total PnL, best/worst trade, streaks shown at top of journal.
- **Manual entry form**: allows adding a trade without a signal — user enters all fields manually.
- **Signal-to-journal**: "Save Trade" button on trade setup card pre-fills form with signal's calculated values.

### Mobile

N/A

## Platform Notes

- `data/trades.json` is local file — no cloud sync. Backup manually.
- Trade IDs are millisecond timestamps — they will collide only if two trades are created in the same millisecond, which is practically impossible for a single-user local tool.

## Related Docs

- `app.py:2595` — `GET /api/trades`
- `app.py:2606` — `POST /api/trades`
- `app.py:2645` — `PUT /api/trades/<id>`
- `app.py:2682` — `GET /api/trades/stats`
- `app.py:43` — `trades_lock`, `TRADES_PATH`, `load_trades()`, `save_trades()`
