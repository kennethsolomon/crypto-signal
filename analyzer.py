"""
analyzer.py - Trading Signal Engine
6-Rule Confluence Framework for Crypto Day Trading
Signal fires when 5/6 rules pass (one miss allowed).
"""

import ccxt
import pandas as pd
import pandas_ta as ta
from datetime import datetime


# ─── Exchange Setup ────────────────────────────────────────────────────────────
exchange = ccxt.bybit({"enableRateLimit": True})

SYMBOLS = ["BTC/USDT", "ETH/USDT", "SOL/USDT", "BNB/USDT", "XRP/USDT", "DOGE/USDT"]

# ─── Rule Configuration ────────────────────────────────────────────────────────
CONFIG = {
    "trend_ema_period": 200,  # 4H EMA period for trend direction
    "rsi_period": 14,  # RSI period
    "rsi_long_min": 50,  # RSI min for long signal
    "rsi_long_max": 70,  # RSI max for long (not overbought)
    "rsi_short_min": 30,  # RSI min for short (not oversold)
    "rsi_short_max": 50,  # RSI max for short signal
    "macd_fast": 12,
    "macd_slow": 26,
    "macd_signal": 9,
    "ema_fast": 9,  # 15M fast EMA
    "ema_slow": 21,  # 15M slow EMA
}


FUNDING_EXTREME_THRESHOLD = 0.0005  # 0.05% — blocks signal on that side
RULE_WEIGHTS = [2.0, 1.5, 1.5, 1.0, 1.0, 1.0]  # Rule1–Rule6; total = 8.0
SIGNAL_THRESHOLD = 5  # 5/6 rules required to fire a signal


def fetch_funding_rate(symbol: str) -> dict:
    """
    Fetch ByBit perpetual funding rate for a symbol.
    Returns extreme=True + blocked_side when rate is dangerously skewed.
    Extreme positive (>= +0.05%): market is overloaded with longs → block longs.
    Extreme negative (<= -0.05%): market is overloaded with shorts → block shorts.
    """
    try:
        # ByBit funding rate requires the perpetual contract symbol format (e.g. BTC/USDT:USDT)
        perp_symbol = (
            symbol.replace("/USDT", "/USDT:USDT") if ":USDT" not in symbol else symbol
        )
        data = exchange.fetch_funding_rate(perp_symbol)
        rate = float(data["fundingRate"])
        if rate >= FUNDING_EXTREME_THRESHOLD:
            return {"rate": rate, "extreme": True, "blocked_side": "LONG"}
        if rate <= -FUNDING_EXTREME_THRESHOLD:
            return {"rate": rate, "extreme": True, "blocked_side": "SHORT"}
        return {"rate": rate, "extreme": False, "blocked_side": None}
    except Exception as e:
        print(f"[WARN] fetch_funding_rate({symbol}): {e}")
        return {"rate": None, "extreme": False, "blocked_side": None}


def fetch_ohlcv(symbol: str, timeframe: str, limit: int = 250) -> pd.DataFrame | None:
    """Fetch OHLCV candles from ByBit. Returns None on failure."""
    try:
        raw = exchange.fetch_ohlcv(symbol, timeframe, limit=limit)
        df = pd.DataFrame(
            raw, columns=["timestamp", "open", "high", "low", "close", "volume"]
        )
        df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
        return df
    except Exception as e:
        print(f"[ERROR] Failed to fetch {symbol} {timeframe}: {e}")
        return None


def check_rule_1_trend(symbol: str) -> dict:
    """
    Rule 1: Trend Alignment
    Timeframe: 4H
    Logic: Price above 200 EMA = bullish trend (LONG only)
           Price below 200 EMA = bearish trend (SHORT only)
    """
    df = fetch_ohlcv(symbol, "4h", 250)
    if df is None or len(df) < 200:
        return {
            "rule": "Trend Alignment (4H EMA 200)",
            "long": False,
            "short": False,
            "value": "Data unavailable",
            "error": True,
        }

    ema200 = ta.ema(df["close"], length=CONFIG["trend_ema_period"])
    price = df["close"].iloc[-1]
    ema_val = ema200.iloc[-1]

    long_pass = price > ema_val
    short_pass = price < ema_val

    distance = abs(float(price) - float(ema_val))
    strength = min(distance / (float(ema_val) * 0.02), 1.0) if ema_val != 0 else 0.0

    return {
        "rule": "Trend Alignment (4H EMA 200)",
        "description": "Trade only with the dominant 4H trend",
        "long": long_pass,
        "short": short_pass,
        "strength": round(float(strength), 3),
        "value": f"Price: {price:,.4f}  |  EMA200: {ema_val:,.4f}",
        "signal_hint": "LONG: Price above EMA200  |  SHORT: Price below EMA200",
        "error": False,
    }


def check_rule_2_rsi(symbol: str) -> dict:
    """
    Rule 2: RSI Momentum
    Timeframe: 1H
    Logic: LONG if RSI is 50–70 and rising
           SHORT if RSI is 30–50 and falling
    """
    df = fetch_ohlcv(symbol, "1h", 100)
    if df is None or len(df) < 20:
        return {
            "rule": "RSI Momentum (1H RSI 14)",
            "long": False,
            "short": False,
            "value": "Data unavailable",
            "error": True,
        }

    df["rsi"] = ta.rsi(df["close"], length=CONFIG["rsi_period"])
    rsi = df["rsi"].iloc[-1]
    rsi_prev = df["rsi"].iloc[-2]

    long_pass = (CONFIG["rsi_long_min"] < rsi < CONFIG["rsi_long_max"]) and (
        rsi > rsi_prev
    )
    short_pass = (CONFIG["rsi_short_min"] < rsi < CONFIG["rsi_short_max"]) and (
        rsi < rsi_prev
    )

    direction = "↑ Rising" if rsi > rsi_prev else "↓ Falling"

    long_mid = (CONFIG["rsi_long_min"] + CONFIG["rsi_long_max"]) / 2
    short_mid = (CONFIG["rsi_short_min"] + CONFIG["rsi_short_max"]) / 2
    long_range = (CONFIG["rsi_long_max"] - CONFIG["rsi_long_min"]) / 2
    short_range = (CONFIG["rsi_short_max"] - CONFIG["rsi_short_min"]) / 2
    if long_pass:
        strength = 1.0 - min(abs(float(rsi) - long_mid) / long_range, 1.0)
    elif short_pass:
        strength = 1.0 - min(abs(float(rsi) - short_mid) / short_range, 1.0)
    else:
        strength = 0.0

    return {
        "rule": "RSI Momentum (1H RSI 14)",
        "description": "Momentum confirmation — not overbought/oversold",
        "long": long_pass,
        "short": short_pass,
        "strength": round(float(strength), 3),
        "value": f"RSI: {rsi:.1f}  |  Prev: {rsi_prev:.1f}  |  {direction}",
        "signal_hint": "LONG: 50–70 rising  |  SHORT: 30–50 falling",
        "error": False,
    }


def check_rule_3_macd(symbol: str) -> dict:
    """
    Rule 3: MACD Histogram State
    Timeframe: 1H
    Logic: LONG if histogram is positive AND growing over last 3 candles
           SHORT if histogram is negative AND falling over last 3 candles
    State-based — persists during trends rather than requiring a rare crossover event.
    """
    df = fetch_ohlcv(symbol, "1h", 100)
    if df is None or len(df) < 30:
        return {
            "rule": "MACD Histogram (1H)",
            "long": False,
            "short": False,
            "value": "Data unavailable",
            "description": "Momentum building in signal direction",
            "signal_hint": "LONG: histogram positive & growing | SHORT: histogram negative & falling",
            "strength": 0.0,
            "error": True,
        }

    macd_data = ta.macd(
        df["close"],
        fast=CONFIG["macd_fast"],
        slow=CONFIG["macd_slow"],
        signal=CONFIG["macd_signal"],
    )
    hist_col = (
        f"MACDh_{CONFIG['macd_fast']}_{CONFIG['macd_slow']}_{CONFIG['macd_signal']}"
    )
    df["histogram"] = macd_data[hist_col]

    h1 = float(df["histogram"].iloc[-1])
    h2 = float(df["histogram"].iloc[-2])
    h3 = float(df["histogram"].iloc[-3])

    # All 3 must be positive AND growing — momentum already established, not just crossing zero
    long_pass = h1 > 0 and h2 > 0 and h3 > 0 and h1 > h2 > h3
    # All 3 must be negative AND falling (more negative) — selling pressure building
    short_pass = h1 < 0 and h2 < 0 and h3 < 0 and h1 < h2 < h3

    if long_pass or short_pass:
        price = float(df["close"].iloc[-1])
        strength = min(abs(h1) / (price * 0.001), 1.0) if price > 0 else 0.0
    else:
        strength = 0.0

    trend = "↑ Growing" if h1 > h2 else "↓ Shrinking"

    return {
        "rule": "MACD Histogram (1H)",
        "description": "Momentum building in signal direction",
        "long": long_pass,
        "short": short_pass,
        "strength": round(float(strength), 3),
        "value": f"Histogram: {h1:.4f}  |  Prev: {h2:.4f}  |  {trend}",
        "signal_hint": "LONG: histogram positive & growing | SHORT: histogram negative & falling",
        "error": False,
    }


def check_rule_4_ema_stack(symbol: str) -> dict:
    """
    Rule 4: EMA Stack
    Timeframe: 15M
    Logic: LONG if Price > EMA9 > EMA21
           SHORT if Price < EMA9 < EMA21
    """
    df = fetch_ohlcv(symbol, "15m", 60)
    if df is None or len(df) < 25:
        return {
            "rule": "EMA Stack (15M 9/21)",
            "long": False,
            "short": False,
            "value": "Data unavailable",
            "error": True,
        }

    df["ema9"] = ta.ema(df["close"], length=CONFIG["ema_fast"])
    df["ema21"] = ta.ema(df["close"], length=CONFIG["ema_slow"])

    price = df["close"].iloc[-1]
    ema9 = df["ema9"].iloc[-1]
    ema21 = df["ema21"].iloc[-1]

    long_pass = price > ema9 > ema21
    short_pass = price < ema9 < ema21

    if long_pass or short_pass:
        spread = abs(float(price) - float(ema21))
        strength = min(spread / (float(ema21) * 0.02), 1.0) if ema21 != 0 else 0.0
    else:
        strength = 0.0

    return {
        "rule": "EMA Stack (15M 9/21)",
        "description": "Short-term price structure aligned with trade direction",
        "long": long_pass,
        "short": short_pass,
        "strength": round(float(strength), 3),
        "value": f"Price: {price:,.4f}  |  EMA9: {ema9:,.4f}  |  EMA21: {ema21:,.4f}",
        "signal_hint": "LONG: Price > EMA9 > EMA21  |  SHORT: Price < EMA9 < EMA21",
        "error": False,
    }


def check_rule_5_volume(symbol: str) -> dict:
    """
    Rule 5: OBV Trend
    Timeframe: 15M
    Logic: On Balance Volume slope positive over 5 candles = net buyers (LONG)
           OBV slope negative over 5 candles = net sellers (SHORT)
    State-based — directional volume pressure rather than single-candle spike.
    """
    df = fetch_ohlcv(symbol, "15m", 60)
    if df is None or len(df) < 10:
        return {
            "rule": "OBV Trend (15M)",
            "long": False,
            "short": False,
            "value": "Data unavailable",
            "description": "Net buying/selling pressure over 5 candles",
            "signal_hint": "LONG: OBV rising (net buyers) | SHORT: OBV falling (net sellers)",
            "strength": 0.0,
            "error": True,
        }

    # Compute OBV manually
    obv = [0.0]
    for i in range(1, len(df)):
        if df["close"].iloc[i] > df["close"].iloc[i - 1]:
            obv.append(obv[-1] + float(df["volume"].iloc[i]))
        elif df["close"].iloc[i] < df["close"].iloc[i - 1]:
            obv.append(obv[-1] - float(df["volume"].iloc[i]))
        else:
            obv.append(obv[-1])

    # Slope over last 5 candles
    slope = (obv[-1] - obv[-5]) / 5

    long_pass = slope > 0
    short_pass = slope < 0

    avg_vol = (
        float(df["volume"].iloc[-20:].mean())
        if len(df) >= 20
        else float(df["volume"].mean())
    )
    strength = min(abs(slope) / avg_vol, 1.0) if avg_vol > 0 else 0.0

    direction = "↑ Rising" if slope > 0 else ("↓ Falling" if slope < 0 else "→ Flat")

    return {
        "rule": "OBV Trend (15M)",
        "description": "Net buying/selling pressure over 5 candles",
        "long": long_pass,
        "short": short_pass,
        "strength": round(float(strength), 3),
        "value": f"OBV: {obv[-1]:,.0f}  |  Slope: {slope:+,.0f}/candle  |  {direction}",
        "signal_hint": "LONG: OBV rising (net buyers) | SHORT: OBV falling (net sellers)",
        "error": False,
    }


def _stoch_rsi_error(value: str) -> dict:
    return {
        "rule": "Stochastic RSI (1H)",
        "long": False,
        "short": False,
        "value": value,
        "description": "Entry timing — buy dips, not tops",
        "signal_hint": "LONG: K<50 crossing up | SHORT: K>50 crossing down",
        "strength": 0.0,
        "error": True,
    }


def check_rule_6_stoch_rsi(symbol: str) -> dict:
    """
    Rule 6: Stochastic RSI Entry Timing
    Timeframe: 1H
    Logic: LONG if K < 50 and K crosses up over D (oversold bounce in uptrend)
           SHORT if K > 50 and K crosses down below D (overbought pullback in downtrend)
    Catches dips within trends — prevents entering at the top of a move.
    """
    df = fetch_ohlcv(symbol, "1h", 60)
    if df is None or len(df) < 20:
        return _stoch_rsi_error("Data unavailable")

    stoch = ta.stochrsi(df["close"], length=14, rsi_length=14, k=3, d=3)
    if stoch is None or stoch.empty:
        return _stoch_rsi_error("Indicator unavailable")

    k_col = "STOCHRSIk_14_14_3_3"
    d_col = "STOCHRSId_14_14_3_3"

    if k_col not in stoch.columns or d_col not in stoch.columns:
        return _stoch_rsi_error("Column unavailable")

    stoch = stoch.dropna()
    if len(stoch) < 2:
        return _stoch_rsi_error("Insufficient data")

    k_cur = float(stoch[k_col].iloc[-1])
    d_cur = float(stoch[d_col].iloc[-1])
    k_prev = float(stoch[k_col].iloc[-2])
    d_prev = float(stoch[d_col].iloc[-2])

    # Crossover: K crosses up = K was <= D before, now K > D
    crosses_up = k_cur > d_cur and k_prev <= d_prev
    crosses_down = k_cur < d_cur and k_prev >= d_prev

    long_pass = k_cur < 50 and crosses_up
    short_pass = k_cur > 50 and crosses_down

    if long_pass:
        strength = min((50 - k_cur) / 50, 1.0)
    elif short_pass:
        strength = min((k_cur - 50) / 50, 1.0)
    else:
        strength = 0.0

    return {
        "rule": "Stochastic RSI (1H)",
        "description": "Entry timing — buy dips, not tops",
        "long": long_pass,
        "short": short_pass,
        "strength": round(float(strength), 3),
        "value": f"K: {k_cur:.1f}  |  D: {d_cur:.1f}  |  K-prev: {k_prev:.1f}",
        "signal_hint": "LONG: K<50 crossing up | SHORT: K>50 crossing down",
        "error": False,
    }


def calculate_trade_setup(
    analysis: dict,
    account_balance: float = 1000.0,
    risk_pct: float = 0.02,
    max_leverage: int = 5,
) -> dict | None:
    """Calculate trade setup with entry, SL, TP levels, position sizing, and leverage."""
    if analysis["signal"] not in ("BUY", "SELL"):
        return None

    entry = analysis["current_price"]
    if entry is None or entry <= 0:
        return None

    direction = "LONG" if analysis["signal"] == "BUY" else "SHORT"
    symbol = analysis["symbol"]

    # ATR-based Stop Loss (adapts to volatility)
    atr_multiplier = 1.5
    sl_distance_abs = entry * 0.015  # fallback 1.5%
    try:
        df = fetch_ohlcv(symbol, "15m", 30)
        if df is not None and len(df) >= 15:
            atr = ta.atr(df["high"], df["low"], df["close"], length=14)
            atr_val = float(atr.iloc[-1])
            if atr_val > 0:
                sl_distance_abs = atr_val * atr_multiplier
    except Exception:
        pass

    # Clamp SL between 0.5% and 5% of entry
    sl_distance_abs = max(sl_distance_abs, entry * 0.005)
    sl_distance_abs = min(sl_distance_abs, entry * 0.05)
    sl_pct = sl_distance_abs / entry

    if direction == "LONG":
        stop_loss = entry - sl_distance_abs
        tp1 = entry + sl_distance_abs
        tp2 = entry + sl_distance_abs * 2
        tp3 = entry + sl_distance_abs * 3
    else:
        stop_loss = entry + sl_distance_abs
        tp1 = entry - sl_distance_abs
        tp2 = entry - sl_distance_abs * 2
        tp3 = entry - sl_distance_abs * 3

    # R:R ratios are fixed by design: 1:1, 1:2, 1:3
    rr1, rr2, rr3 = 1.0, 2.0, 3.0
    tp1_pct = round(sl_pct * 100, 2)
    tp2_pct = round(sl_pct * 2 * 100, 2)
    tp3_pct = round(sl_pct * 3 * 100, 2)

    # Position sizing based on risk
    risk_amount = account_balance * risk_pct
    position_size_usdt = risk_amount / sl_pct if sl_pct > 0 else 0
    position_size_coin = position_size_usdt / entry if entry > 0 else 0

    # Leverage: auto-calculated 2x-5x based on SL distance
    leverage = min(max(2, round(1 / sl_pct)), max_leverage)

    return {
        "symbol": symbol,
        "direction": direction,
        "entry_price": round(entry, 6),
        "stop_loss": round(stop_loss, 6),
        "sl_pct": round(sl_pct * 100, 2),
        "tp1": round(tp1, 6),
        "tp2": round(tp2, 6),
        "tp3": round(tp3, 6),
        "tp1_pct": tp1_pct,
        "tp2_pct": tp2_pct,
        "tp3_pct": tp3_pct,
        "rr1": rr1,
        "rr2": rr2,
        "rr3": rr3,
        "leverage": leverage,
        "risk_amount": round(risk_amount, 2),
        "position_size_usdt": round(position_size_usdt, 2),
        "position_size_coin": round(position_size_coin, 6),
        "account_balance": account_balance,
        "risk_pct": risk_pct,
        "confidence_score": analysis["confidence_score"],
        "confidence_label": analysis["confidence_label"],
        "timestamp": analysis["timestamp_display"],
    }


def get_chart_data(
    symbol: str, timeframe: str = "15m", limit: int = 100
) -> dict | None:
    """Return OHLCV + EMA9/EMA21 for charting."""
    df = fetch_ohlcv(symbol, timeframe, limit)
    if df is None or len(df) < 25:
        return None

    df["ema9"] = ta.ema(df["close"], length=9)
    df["ema21"] = ta.ema(df["close"], length=21)

    candles = []
    ema9_data = []
    ema21_data = []
    for _, row in df.iterrows():
        t = int(row["timestamp"].timestamp())
        candles.append(
            {
                "time": t,
                "open": float(row["open"]),
                "high": float(row["high"]),
                "low": float(row["low"]),
                "close": float(row["close"]),
            }
        )
        if pd.notna(row["ema9"]):
            ema9_data.append({"time": t, "value": float(row["ema9"])})
        if pd.notna(row["ema21"]):
            ema21_data.append({"time": t, "value": float(row["ema21"])})

    return {"candles": candles, "ema9": ema9_data, "ema21": ema21_data}


def analyze(symbol: str) -> dict:
    """
    Run all 6 rules for a given symbol.
    Signal fires when 5/6 rules pass (one miss allowed).
    Funding rate acts as a hard block on extreme values.
    """
    print(f"[{datetime.now().strftime('%H:%M:%S')}] Analyzing {symbol}...")

    rules = [
        check_rule_1_trend(symbol),
        check_rule_2_rsi(symbol),
        check_rule_3_macd(symbol),
        check_rule_4_ema_stack(symbol),
        check_rule_5_volume(symbol),
        check_rule_6_stoch_rsi(symbol),
    ]

    total_weight = sum(RULE_WEIGHTS)

    # Convert numpy types to native Python types for JSON serialization
    for r in rules:
        r["long"] = bool(r["long"])
        r["short"] = bool(r["short"])
        r["strength"] = float(r.get("strength", 0.0))
        if "error" in r:
            r["error"] = bool(r["error"])

    rules_long = [r["long"] for r in rules]
    rules_short = [r["short"] for r in rules]

    long_count = int(sum(rules_long))
    short_count = int(sum(rules_short))
    total = len(rules)

    # Signal threshold: 5/6 rules required (one miss allowed)
    if long_count >= SIGNAL_THRESHOLD and long_count > short_count:
        signal = "BUY"
        signal_color = "green"
    elif short_count >= SIGNAL_THRESHOLD and short_count > long_count:
        signal = "SELL"
        signal_color = "red"
    elif long_count >= SIGNAL_THRESHOLD and short_count >= SIGNAL_THRESHOLD:
        # Tie — conflicting signals, wait
        signal = "WAIT"
        signal_color = "gray"
    else:
        signal = "WAIT"
        signal_color = "gray"

    # Funding rate hard block
    funding_info = fetch_funding_rate(symbol)
    funding_rate = funding_info["rate"]
    funding_blocked = funding_info["blocked_side"]
    signal_blocked_reason = None

    if funding_blocked == "LONG" and signal == "BUY":
        signal = "WAIT"
        signal_color = "gray"
        signal_blocked_reason = "Extreme positive funding — long squeeze risk"
    elif funding_blocked == "SHORT" and signal == "SELL":
        signal = "WAIT"
        signal_color = "gray"
        signal_blocked_reason = "Extreme negative funding — short squeeze risk"

    # Weighted confidence score
    long_confidence = (
        sum(
            r["strength"] * w
            for r, w, passes in zip(rules, RULE_WEIGHTS, rules_long)
            if passes
        )
        / total_weight
        * 100
    )
    short_confidence = (
        sum(
            r["strength"] * w
            for r, w, passes in zip(rules, RULE_WEIGHTS, rules_short)
            if passes
        )
        / total_weight
        * 100
    )

    if signal == "BUY":
        confidence_score = round(long_confidence, 1)
    elif signal == "SELL":
        confidence_score = round(short_confidence, 1)
    else:
        confidence_score = round(max(long_confidence, short_confidence), 1)

    if confidence_score >= 85:
        confidence_label = "Strong"
        confidence_color = "green"
    elif confidence_score >= 70:
        confidence_label = "Medium"
        confidence_color = "yellow"
    else:
        confidence_label = "Weak"
        confidence_color = "gray"

    # Forming detection: 4+ rules passing = heads up (5/6 = real signal; 5/5 tie stays WAIT)
    forming = False
    forming_direction = None
    if signal == "WAIT":
        if long_count >= 4 or short_count >= 4:
            forming = True
            if long_count >= short_count:
                forming_direction = "LONG"
            else:
                forming_direction = "SHORT"

    # Get current price
    try:
        price_df = fetch_ohlcv(symbol, "1m", 2)
        current_price = (
            float(price_df["close"].iloc[-1]) if price_df is not None else None
        )
    except Exception:
        current_price = None

    return {
        "symbol": symbol,
        "signal": signal,
        "signal_color": signal_color,
        "rules": rules,
        "long_rules_met": long_count,
        "short_rules_met": short_count,
        "total_rules": total,
        "confidence_score": confidence_score,
        "confidence_label": confidence_label,
        "confidence_color": confidence_color,
        "forming": forming,
        "forming_direction": forming_direction,
        "funding_rate": funding_rate,
        "funding_blocked": funding_blocked,
        "signal_blocked_reason": signal_blocked_reason,
        "current_price": current_price,
        "timestamp": datetime.now().isoformat(),
        "timestamp_display": datetime.now().strftime("%Y-%m-%d %H:%M:%S UTC"),
    }
