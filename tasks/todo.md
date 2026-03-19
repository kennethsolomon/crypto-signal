# TODO — 2026-03-19 — Crypto Signal Dashboard v2 (ByBit Trading Suite)

## Goal
Transform the 5-rule confluence dashboard into a complete ByBit futures trading assistant with confidence-scored signals, copy-paste trade setups, a built-in guide, and a trade journal — optimized for daily trading with minimal screen time.

## Plan

### Milestone 1: Smarter Signals (Confidence Scoring + Real-Time Feel)

#### Wave 0 (prerequisite — exchange switch)
- [x] **0.1** Switch exchange from Binance to ByBit in `analyzer.py:14` (`ccxt.binance` → `ccxt.bybit`) — prices will match user's trading platform exactly
- [x] **0.2** Update dashboard header text from "Live via Binance" to "Live via ByBit" in `app.py`
- [x] **0.3** Update Framework Settings panel "Data Source" from "Binance (Free API)" to "ByBit (Free API)"

#### Wave 1 (parallel — backend, depends on Wave 0)
- [x] **1.1** Add rule strength scoring to `analyzer.py` — each rule returns `strength: float` (0.0–1.0) based on distance from threshold, not just pass/fail
  - Rule 1 (Trend): strength = abs(price - ema200) / (ema200 * 0.02), capped at 1.0
  - Rule 2 (RSI): strength = distance from threshold midpoint (e.g., RSI 60 in 50-70 range = 0.5)
  - Rule 3 (MACD): strength = 1.0 for fresh crossover (this candle), 0.66 for 1 candle ago, 0.33 for 2 candles ago
  - Rule 4 (EMA Stack): strength = spread between Price/EMA9/EMA21 normalized
  - Rule 5 (Volume): strength = (ratio - 1.0) / 1.0, capped at 1.0 (ratio 2.2 = 1.0, ratio 1.2 = 0.2)
- [x] **1.2** Add weighted confidence score to `analyze()` return value
  - Weights: Rule 1 = 2.0, Rules 2-3 = 1.5 each, Rules 4-5 = 1.0 each (total weight = 7.0)
  - Formula: `confidence = sum(strength_i * weight_i) / sum(weight_i) * 100`
  - Return: `confidence_score`, `confidence_label` (Strong/Medium/Weak), `confidence_color`
  - Staging: >=85% Green/Strong, 70-84% Yellow/Medium, <70% Gray/Weak
- [x] **1.3** Add "signal forming" detection — return `forming: true` + `forming_direction` when 3-4/5 rules pass (heads-up before full signal)

#### Wave 2 (depends on 1.1–1.3 — frontend)
- [x] **1.4** Update signal card UI to show confidence score, strength label, and color-coded confidence bar
- [x] **1.5** Add per-rule strength bars in the rules panel (mini progress bar next to each rule showing 0-100% strength)
- [x] **1.6** Add "Signal Forming" alert banner — yellow pulsing banner at top when 3-4 rules pass ("BTC/USDT: 4/5 rules passing for LONG — watch closely")
- [x] **1.7** Add refresh mode toggle in header — "Real-Time" (10s) vs "Polling" (60s). Default to Polling. User switches to Real-Time when actively watching for entries. Saves to settings so it persists. Updates `CACHE_TTL` dynamically.

---

### Milestone 2: Trade Setup Card + Copy-to-Clipboard + Guide

#### Wave 3 (parallel — backend)
- [x] **2.1** Add trade setup calculator to `analyzer.py` — new function `calculate_trade_setup(analysis, account_balance, risk_pct)` returning:
  - `entry_price`: current market price
  - `stop_loss`: recent swing low/high from 15M data (or 1.5% fallback)
  - `tp1`, `tp2`, `tp3`: entry +/- 2%, 5%, 8% respectively
  - `sl_pct`: percentage distance to stop loss
  - `position_size`: `(account_balance * risk_pct) / sl_distance`
  - `position_size_coin`: position in coin units
  - `leverage`: min(max(2, round(1 / sl_pct)), 5) — auto-calculated 2x-5x based on SL distance
  - `risk_reward`: array of R:R for each TP level
- [x] **2.2** Add `/api/trade-setup` endpoint accepting `symbol`, `balance` (default 1000), `risk_pct` (default 0.02)
- [x] **2.3** Add user settings persistence — `data/settings.json` storing: `account_balance`, `risk_pct`, `max_leverage`

#### Wave 4 (depends on 2.1–2.3 — frontend)
- [x] **2.4** Add Trade Setup Card below signal card showing: Entry, SL, TP1/TP2/TP3, Leverage, Position Size, Risk Amount, R:R ratios
- [x] **2.5** Add "Copy Trade Setup" button — copies multi-line format to clipboard:
  ```
  === TRADE SETUP ===
  Pair:       BTC/USDT
  Direction:  LONG
  Entry:      $67,250.00
  Stop Loss:  $65,850.00 (-2.08%)
  TP1:        $68,595.00 (+2.00%)
  TP2:        $70,612.50 (+5.00%)
  TP3:        $72,630.00 (+8.00%)
  Leverage:   3x
  Size:       0.015 BTC ($1,008.75)
  Risk:       2% of balance
  Confidence: 87% (Strong)
  Signal:     2026-03-19 14:30 UTC
  ===================
  ```
- [x] **2.6** Add Settings panel (right column) — input fields for: Account Balance (USDT), Risk % per trade, Max Leverage — auto-saved to backend
- [x] **2.7** Add Trading Guide panel (collapsible, right column) — explains:
  - How the 5-rule framework works
  - What each confidence level means
  - How to read the trade setup card
  - Step-by-step: "How to place this trade on ByBit"
  - Risk management basics (never risk >2%, always use SL)
  - When to take profit (scale out at TP1/TP2/TP3)

---

### Milestone 3: Trade Journal + Performance Tracking

#### Wave 5 (parallel — backend)
- [x] **3.1** Create `data/trades.json` persistence layer — functions: `save_trade()`, `load_trades()`, `update_trade()`, `close_trade()`
- [x] **3.2** Add trade data model:
  ```
  {id, symbol, direction, entry_price, stop_loss, tp1, tp2, tp3,
   leverage, position_size, risk_pct, confidence_score,
   status: "open"|"closed", exit_price, exit_reason,
   pnl_usdt, pnl_pct, opened_at, closed_at, notes}
  ```
- [x] **3.3** Add API endpoints:
  - `POST /api/trades` — log a new trade (from trade setup card or manual)
  - `GET /api/trades` — list all trades (filterable: open/closed/all)
  - `PUT /api/trades/<id>` — update trade (close it, add exit price/notes)
  - `GET /api/trades/stats` — aggregate stats (win rate, avg R:R, total P&L, streak)

#### Wave 6 (depends on 3.1–3.3 — frontend)
- [x] **3.4** Add "Log This Trade" button on trade setup card — one click to save the current signal as an open trade
- [x] **3.5** Add Trade Journal panel (new tab or section) showing:
  - Open trades with live P&L (current price vs entry)
  - Closed trades with final P&L
  - Inline "Close Trade" button with exit price input
- [x] **3.6** Add Performance Stats panel:
  - Total trades, Win rate, Average R:R
  - Total P&L (USDT and %)
  - Best/worst trade
  - Current streak (wins/losses)
  - Simple equity curve (if enough data)
- [x] **3.7** Migrate signal history from in-memory to `data/signals.json` so it survives restarts

---

### Milestone 4: Polish + Final Touches

#### Wave 7 (parallel — cleanup)
- [x] **4.1** Add browser notification (Notification API) when a signal fires or is forming — user gets alerted even if tab is in background
- [x] **4.2** Add audio alert (optional beep) on new signal
- [x] **4.3** Create `data/` directory on startup if missing, add to `.gitignore`
- [x] **4.4** Update README.md with new features documentation
- [x] **4.5** Test full flow end-to-end: signal forms → alert → trade setup → copy → log trade → close trade → view stats

## Verification
- `python app.py` → starts without errors on port 5001
- `curl localhost:5001/api/analyze?symbol=BTC/USDT` → response includes `confidence_score`, `strength` per rule, `forming` field
- `curl localhost:5001/api/trade-setup?symbol=BTC/USDT&balance=1000` → returns entry, SL, TP1-3, leverage, position size
- `curl -X POST localhost:5001/api/trades -H 'Content-Type: application/json' -d '{...}'` → saves trade to data/trades.json
- `curl localhost:5001/api/trades/stats` → returns win rate, P&L, R:R stats
- Open browser → see confidence score, trade setup card, copy button works, guide panel visible
- Click "Log This Trade" → trade appears in journal
- Close trade → P&L calculated and displayed in stats

## Acceptance Criteria
- [ ] Confidence scoring works — each rule has strength 0.0–1.0, aggregate weighted score shown
- [ ] "Signal Forming" alert appears when 3-4/5 rules pass
- [ ] Trade setup card shows entry, SL, TP1/TP2/TP3, leverage (2-5x), position size
- [ ] Copy-to-clipboard produces multi-line format in one click
- [ ] Settings panel stores account balance, risk %, max leverage (persisted)
- [ ] Built-in trading guide explains the framework and ByBit placement steps
- [ ] Trade journal logs/closes trades with P&L calculation
- [ ] Performance stats show win rate, avg R:R, total P&L
- [ ] Signal and trade data persists to disk (survives restart)
- [ ] 10-second refresh cycle feels real-time
- [ ] Browser notifications fire on new signal or signal forming

## Risks / Unknowns
- ByBit rate limits at 10s polling across 6 symbols — mitigated by UI toggle (user chooses Real-Time 10s vs Polling 60s)
- Swing high/low SL calculation may be unreliable on low-volume pairs (fallback to fixed 1.5%)
- Browser Notification API requires user permission (graceful fallback if denied)
- In-memory + JSON persistence is fine for single user but won't scale (acceptable for personal tool)

## Results
- (fill after execution)

## Errors
| Error | Attempt | Resolution |
|-------|---------|------------|
|       | 1       |            |
