"""
analyzer.py - Trading Signal Engine
5-Rule Confluence Framework for Crypto Day Trading
Signals only fire when ALL rules are met.
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
    "trend_ema_period": 200,       # 4H EMA period for trend direction
    "rsi_period": 14,              # RSI period
    "rsi_long_min": 50,            # RSI min for long signal
    "rsi_long_max": 70,            # RSI max for long (not overbought)
    "rsi_short_min": 30,           # RSI min for short (not oversold)
    "rsi_short_max": 50,           # RSI max for short signal
    "macd_fast": 12,
    "macd_slow": 26,
    "macd_signal": 9,
    "macd_lookback": 3,            # How many candles back to look for crossover
    "ema_fast": 9,                 # 15M fast EMA
    "ema_slow": 21,                # 15M slow EMA
    "volume_multiplier": 1.2,      # Volume must be this x the average
    "volume_avg_period": 20,       # Period for average volume
}


def fetch_ohlcv(symbol: str, timeframe: str, limit: int = 250) -> pd.DataFrame | None:
    """Fetch OHLCV candles from ByBit. Returns None on failure."""
    try:
        raw = exchange.fetch_ohlcv(symbol, timeframe, limit=limit)
        df = pd.DataFrame(raw, columns=["timestamp", "open", "high", "low", "close", "volume"])
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
        return {"rule": "Trend Alignment (4H EMA 200)", "long": False, "short": False,
                "value": "Data unavailable", "error": True}

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
        return {"rule": "RSI Momentum (1H RSI 14)", "long": False, "short": False,
                "value": "Data unavailable", "error": True}

    df["rsi"] = ta.rsi(df["close"], length=CONFIG["rsi_period"])
    rsi = df["rsi"].iloc[-1]
    rsi_prev = df["rsi"].iloc[-2]

    long_pass = (CONFIG["rsi_long_min"] < rsi < CONFIG["rsi_long_max"]) and (rsi > rsi_prev)
    short_pass = (CONFIG["rsi_short_min"] < rsi < CONFIG["rsi_short_max"]) and (rsi < rsi_prev)

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
    Rule 3: MACD Crossover
    Timeframe: 1H
    Logic: LONG if MACD crossed above signal in last 3 candles
           SHORT if MACD crossed below signal in last 3 candles
    """
    df = fetch_ohlcv(symbol, "1h", 100)
    if df is None or len(df) < 30:
        return {"rule": "MACD Crossover (1H)", "long": False, "short": False,
                "value": "Data unavailable", "error": True}

    macd_data = ta.macd(df["close"],
                        fast=CONFIG["macd_fast"],
                        slow=CONFIG["macd_slow"],
                        signal=CONFIG["macd_signal"])
    df["macd"] = macd_data[f"MACD_{CONFIG['macd_fast']}_{CONFIG['macd_slow']}_{CONFIG['macd_signal']}"]
    df["sig"] = macd_data[f"MACDs_{CONFIG['macd_fast']}_{CONFIG['macd_slow']}_{CONFIG['macd_signal']}"]

    macd_long = False
    macd_short = False
    long_strength = 0.0
    short_strength = 0.0
    lookback = CONFIG["macd_lookback"]
    freshness_scores = [1.0, 0.66, 0.33]

    for idx, i in enumerate(range(-1, -lookback - 1, -1)):
        cur_macd = df["macd"].iloc[i]
        cur_sig = df["sig"].iloc[i]
        prev_macd = df["macd"].iloc[i - 1]
        prev_sig = df["sig"].iloc[i - 1]
        if cur_macd > cur_sig and prev_macd <= prev_sig:
            macd_long = True
            long_strength = max(long_strength, freshness_scores[idx])
        if cur_macd < cur_sig and prev_macd >= prev_sig:
            macd_short = True
            short_strength = max(short_strength, freshness_scores[idx])

    strength = max(long_strength, short_strength)

    cur_macd_val = df["macd"].iloc[-1]
    cur_sig_val = df["sig"].iloc[-1]
    above = "MACD above Signal" if cur_macd_val > cur_sig_val else "MACD below Signal"

    return {
        "rule": "MACD Crossover (1H)",
        "description": "Momentum shift confirmation via crossover",
        "long": macd_long,
        "short": macd_short,
        "strength": round(float(strength), 3),
        "value": f"MACD: {cur_macd_val:.4f}  |  Signal: {cur_sig_val:.4f}  |  {above}",
        "signal_hint": f"Crossover within last {lookback} candles",
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
        return {"rule": "EMA Stack (15M 9/21)", "long": False, "short": False,
                "value": "Data unavailable", "error": True}

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
    Rule 5: Volume Surge
    Timeframe: 15M
    Logic: Current candle volume > 1.2× the 20-period average
    """
    df = fetch_ohlcv(symbol, "15m", 60)
    if df is None or len(df) < 22:
        return {"rule": "Volume Surge (15M 1.2×)", "long": False, "short": False,
                "value": "Data unavailable", "error": True}

    avg_vol = df["volume"].iloc[-CONFIG["volume_avg_period"] - 1:-1].mean()
    cur_vol = df["volume"].iloc[-1]
    ratio = cur_vol / avg_vol if avg_vol > 0 else 0

    surge = ratio >= CONFIG["volume_multiplier"]
    strength = min((float(ratio) - 1.0) / 1.0, 1.0) if ratio > 1.0 else 0.0

    return {
        "rule": "Volume Surge (15M 1.2×)",
        "description": "Real buying/selling pressure backing the move",
        "long": surge,
        "short": surge,
        "strength": round(float(strength), 3),
        "value": f"Volume: {cur_vol:,.0f}  |  Avg: {avg_vol:,.0f}  |  Ratio: {ratio:.2f}×",
        "signal_hint": f"Current volume must be ≥ {CONFIG['volume_multiplier']}× the {CONFIG['volume_avg_period']}-candle average",
        "error": False,
    }


def calculate_trade_setup(analysis: dict, account_balance: float = 1000.0,
                          risk_pct: float = 0.02, max_leverage: int = 5) -> dict | None:
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
        tp1 = entry + sl_distance_abs * 1  # 1:1 R:R
        tp2 = entry + sl_distance_abs * 2  # 1:2 R:R
        tp3 = entry + sl_distance_abs * 3  # 1:3 R:R
    else:
        stop_loss = entry + sl_distance_abs
        tp1 = entry - sl_distance_abs * 1  # 1:1 R:R
        tp2 = entry - sl_distance_abs * 2  # 1:2 R:R
        tp3 = entry - sl_distance_abs * 3  # 1:3 R:R

    # R:R ratios are fixed by design: 1:1, 1:2, 1:3
    rr1, rr2, rr3 = 1.0, 2.0, 3.0
    tp1_pct = round(sl_pct * 1 * 100, 2)
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


def get_chart_data(symbol: str, timeframe: str = "15m", limit: int = 100) -> dict | None:
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
        candles.append({
            "time": t,
            "open": float(row["open"]),
            "high": float(row["high"]),
            "low": float(row["low"]),
            "close": float(row["close"]),
        })
        if pd.notna(row["ema9"]):
            ema9_data.append({"time": t, "value": float(row["ema9"])})
        if pd.notna(row["ema21"]):
            ema21_data.append({"time": t, "value": float(row["ema21"])})

    return {"candles": candles, "ema9": ema9_data, "ema21": ema21_data}


def analyze(symbol: str) -> dict:
    """
    Run all 5 rules for a given symbol.
    Returns full analysis including signal decision and individual rule results.
    """
    print(f"[{datetime.now().strftime('%H:%M:%S')}] Analyzing {symbol}...")

    rules = [
        check_rule_1_trend(symbol),
        check_rule_2_rsi(symbol),
        check_rule_3_macd(symbol),
        check_rule_4_ema_stack(symbol),
        check_rule_5_volume(symbol),
    ]

    # Rule weights: Rule1=2.0, Rule2=1.5, Rule3=1.5, Rule4=1.0, Rule5=1.0
    RULE_WEIGHTS = [2.0, 1.5, 1.5, 1.0, 1.0]
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

    all_long = all(rules_long)
    all_short = all(rules_short)

    if all_long:
        signal = "BUY"
        signal_color = "green"
    elif all_short:
        signal = "SELL"
        signal_color = "red"
    else:
        signal = "WAIT"
        signal_color = "gray"

    # Weighted confidence score
    long_confidence = sum(
        r["strength"] * w for r, w, passes in zip(rules, RULE_WEIGHTS, rules_long) if passes
    ) / total_weight * 100
    short_confidence = sum(
        r["strength"] * w for r, w, passes in zip(rules, RULE_WEIGHTS, rules_short) if passes
    ) / total_weight * 100

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

    # Signal forming detection (3-4 rules passing = heads up)
    forming = False
    forming_direction = None
    if not all_long and not all_short:
        if 3 <= long_count <= 4:
            forming = True
            forming_direction = "LONG"
        elif 3 <= short_count <= 4:
            forming = True
            forming_direction = "SHORT"

    # Get current price
    try:
        price_df = fetch_ohlcv(symbol, "1m", 2)
        current_price = float(price_df["close"].iloc[-1]) if price_df is not None else None
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
        "current_price": current_price,
        "timestamp": datetime.now().isoformat(),
        "timestamp_display": datetime.now().strftime("%Y-%m-%d %H:%M:%S UTC"),
    }
