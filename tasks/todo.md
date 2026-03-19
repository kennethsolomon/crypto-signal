# TODO — 2026-03-19 — Signal Rule Upgrade (Option B)

## Goal
Upgrade the 5-rule confluence system to a 6-rule state-based system. Replace the two event-based rules (MACD Crossover, Volume Surge) with state-based equivalents that persist during trends. Add Stochastic RSI for entry timing and a ByBit Funding Rate hard block filter. Require 5/6 rules to fire a signal.

## Context
All Milestone 1-4 tasks from the original plan are complete. This plan addresses a new problem: the system never fires because Rules 3 and 5 are event-based and almost never coincide with the other 3 state-based rules in real market conditions.

## Plan

### Wave 1 (parallel — backend, all in analyzer.py)

- [x] **1.1** Replace `check_rule_3_macd()` logic — MACD Crossover → MACD Histogram State
  - New logic: MACD histogram must be **positive AND growing** (increasing) over the last 3 consecutive candles
  - LONG pass: histogram[-1] > 0 AND histogram[-1] > histogram[-2] > histogram[-3]
  - SHORT pass: histogram[-1] < 0 AND histogram[-1] < histogram[-2] < histogram[-3]
  - Strength: abs(histogram[-1]) normalized by current price * 0.001, capped at 1.0
  - Update rule name to `"MACD Histogram (1H)"`, description to `"Momentum building in signal direction"`
  - signal_hint: `"LONG: histogram positive & growing | SHORT: histogram negative & falling"`

- [x] **1.2** Replace `check_rule_5_volume()` logic — Volume Surge → OBV Trend
  - New logic: On Balance Volume (OBV) must be sloping in the signal direction over last 5 candles
  - Calculate OBV manually: `obv[i] = obv[i-1] + volume[i]` if close[i] > close[i-1] else `obv[i-1] - volume[i]`
  - LONG pass: linear slope of OBV over last 5 candles is positive (OBV trending up = net buying)
  - SHORT pass: linear slope of OBV over last 5 candles is negative (OBV trending down = net selling)
  - Slope: `(obv[-1] - obv[-5]) / 5` — positive = buying pressure, negative = selling pressure
  - Strength: abs(slope) normalized by average volume, capped at 1.0
  - Update rule name to `"OBV Trend (15M)"`, description to `"Net buying/selling pressure over 5 candles"`
  - signal_hint: `"LONG: OBV rising (net buyers) | SHORT: OBV falling (net sellers)"`

- [x] **1.3** Add new `check_rule_6_stoch_rsi(symbol)` function
  - Timeframe: 1H, fetch 60 candles
  - Calculate RSI(14) first, then Stochastic of RSI: `stoch_k = (rsi - rsi_min_14) / (rsi_max_14 - rsi_min_14) * 100` over 14-period window, then smooth with 3-period SMA for K and D lines
  - Use `pandas_ta.stochrsi(close, length=14, rsi_length=14, k=3, d=3)` — returns STOCHRSId and STOCHRSIk columns
  - LONG pass: K < 50 AND K is crossing up over D (K[-1] > D[-1] AND K[-2] <= D[-2]) — oversold bounce in uptrend
  - SHORT pass: K > 50 AND K is crossing down below D (K[-1] < D[-1] AND K[-2] >= D[-2]) — overbought pullback in downtrend
  - Strength: for long — (50 - K) / 50 capped at 1.0 (lower K = stronger oversold bounce). For short — (K - 50) / 50 capped at 1.0
  - Return dict with standard rule fields: rule, description, long, short, strength, value, signal_hint, error

- [x] **1.4** Add `fetch_funding_rate(symbol)` helper function
  - Call `exchange.fetch_funding_rate(symbol)` — returns ccxt funding rate dict
  - Extract `fundingRate` field (float, e.g. 0.0001 = 0.01%)
  - Handle exceptions: return None on failure (ccxt error, unsupported symbol)
  - Thresholds: extreme_positive = 0.0005 (0.05%), extreme_negative = -0.0005
  - Return dict: `{rate: float|None, extreme: bool, direction: "long"|"short"|None, blocked_side: "LONG"|"SHORT"|None}`

### Wave 2 (depends on Wave 1 — update core analyze() function)

- [x] **2.1** Update `analyze()` in analyzer.py
  - Add `check_rule_6_stoch_rsi(symbol)` to rules list (6 rules total)
  - Update `RULE_WEIGHTS` to `[2.0, 1.5, 1.5, 1.0, 1.0, 1.0]`, total_weight = 8.0
  - **Change signal threshold:** Replace `all(rules_long)` / `all(rules_short)` with `long_count >= 5` / `short_count >= 5` (5/6 minimum)
  - Resolve conflict: if both long_count >= 5 and short_count >= 5, use whichever is higher; if tie, WAIT
  - **Add funding rate check:** Call `fetch_funding_rate(symbol)`, add `funding_rate` and `funding_blocked` to return value
  - If `funding_blocked == "LONG"` and signal would be BUY: override to WAIT, set `signal_blocked_reason = "Extreme positive funding — long squeeze risk"`
  - If `funding_blocked == "SHORT"` and signal would be SELL: override to WAIT, set `signal_blocked_reason = "Extreme negative funding — short squeeze risk"`
  - **Update forming detection:** forming = True when 4/6 or 5/6 rules pass (but not signal threshold)
  - forming triggers at: `4 <= long_count <= 5` or `4 <= short_count <= 5`
  - Add `funding_rate`, `funding_blocked`, `signal_blocked_reason` to return dict
  - Update `total_rules` field from 5 to 6

### Wave 3 (depends on Wave 2 — frontend updates in app.py DASHBOARD_HTML)

- [x] **3.1** Update rules panel to show 6 rules
  - Add row for Rule 6: Stochastic RSI with rule name, description, signal_hint, strength bar
  - Find all instances of `"5/5"`, `"X/5"`, `"/5 rules"` in the JS/HTML and update to `"6"` and `"/6 rules"`
  - Update "Signal Forming" banner text: was `"4/5 rules"` → `"5/6 rules"` (still 4 or 5 rules passing)

- [x] **3.2** Add Funding Rate badge in signal card area
  - Show current funding rate as a small badge below or beside the confidence score
  - Format: `"Funding: +0.012%"` in green if neutral, yellow if approaching threshold (>0.03%), red + "BLOCKED" if extreme
  - If `funding_blocked`: show a warning banner `"⚠ Long blocked — extreme funding rate (+0.05%)"` in red
  - If funding data unavailable (None): show `"Funding: N/A"` in gray

- [x] **3.3** Update trading guide to explain new rules
  - Replace MACD Crossover explanation with MACD Histogram State explanation
  - Replace Volume Surge explanation with OBV Trend explanation
  - Add Stochastic RSI section: explain what it catches (oversold bounce = buy the dip, not the top)
  - Add Funding Rate section: explain what it is and why extreme funding = danger

---

## Verification

```bash
# Backend: rule functions work
python -c "from analyzer import check_rule_3_macd; r=check_rule_3_macd('BTC/USDT'); print(r['rule'], r['long'], r['short'], r['strength'])"
python -c "from analyzer import check_rule_5_volume; r=check_rule_5_volume('BTC/USDT'); print(r['rule'], r['long'], r['short'], r['strength'])"
python -c "from analyzer import check_rule_6_stoch_rsi; r=check_rule_6_stoch_rsi('BTC/USDT'); print(r['rule'], r['long'], r['short'], r['strength'])"
python -c "from analyzer import fetch_funding_rate; print(fetch_funding_rate('BTC/USDT'))"

# Backend: full analyze() with 6 rules
python -c "
from analyzer import analyze
r = analyze('BTC/USDT')
print('Rules met (long):', r['long_rules_met'], '/', r['total_rules'])
print('Signal:', r['signal'])
print('Funding rate:', r['funding_rate'])
print('Funding blocked:', r['funding_blocked'])
print('Rule names:', [ru['rule'] for ru in r['rules']])
"

# Server: start without errors
python app.py &
sleep 3
curl -s localhost:5001/api/analyze?symbol=BTC/USDT | python -m json.tool | grep -E "signal|total_rules|long_rules_met|funding"
```

## Acceptance Criteria

- [ ] Rule 3 name is `"MACD Histogram (1H)"` — no longer "MACD Crossover"
- [ ] Rule 5 name is `"OBV Trend (15M)"` — no longer "Volume Surge"
- [ ] Rule 6 exists: `"Stochastic RSI (1H)"` with long/short/strength fields
- [ ] `analyze()` returns `total_rules: 6`
- [ ] Signal fires when `long_rules_met >= 5` or `short_rules_met >= 5`
- [ ] Forming detected at 4 or 5 rules passing (not 3)
- [ ] `funding_rate` and `funding_blocked` present in analyze() response
- [ ] Extreme funding (>0.05%) blocks signal on correct side
- [ ] Dashboard shows 6 rule rows in the rules panel
- [ ] Funding rate badge visible in signal card
- [ ] "X/6 rules" shown everywhere (was "X/5")
- [ ] Running `python app.py` starts without errors
- [ ] At least one coin shows 4/6 or 5/6 rules passing (forming state)

## Risks / Unknowns

- `exchange.fetch_funding_rate()` may not be supported for all symbols on ByBit's free API tier — handle gracefully (None = neutral, don't block)
- `pandas_ta.stochrsi()` column naming may differ by version — check exact column names at runtime and handle both formats
- Changing signal threshold from 5/5 to 5/6 means two directional signals could theoretically both reach 5/6 simultaneously — resolve by using whichever has more rules or WAIT on tie

## Results
- (fill after execution)

## Errors
| Error | Attempt | Resolution |
|-------|---------|------------|
|       | 1       |            |
