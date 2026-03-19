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
exchange = ccxt.binance({"enableRateLimit": True})

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
    """Fetch OHLCV candles from Binance. Returns None on failure."""
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

    return {
        "rule": "Trend Alignment (4H EMA 200)",
        "description": "Trade only with the dominant 4H trend",
        "long": long_pass,
        "short": short_pass,
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

    return {
        "rule": "RSI Momentum (1H RSI 14)",
        "description": "Momentum confirmation — not overbought/oversold",
        "long": long_pass,
        "short": short_pass,
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
    lookback = CONFIG["macd_lookback"]

    for i in range(-lookback, 0):
        cur_macd = df["macd"].iloc[i]
        cur_sig = df["sig"].iloc[i]
        prev_macd = df["macd"].iloc[i - 1]
        prev_sig = df["sig"].iloc[i - 1]
        if cur_macd > cur_sig and prev_macd <= prev_sig:
            macd_long = True
        if cur_macd < cur_sig and prev_macd >= prev_sig:
            macd_short = True

    cur_macd_val = df["macd"].iloc[-1]
    cur_sig_val = df["sig"].iloc[-1]
    above = "MACD above Signal" if cur_macd_val > cur_sig_val else "MACD below Signal"

    return {
        "rule": "MACD Crossover (1H)",
        "description": "Momentum shift confirmation via crossover",
        "long": macd_long,
        "short": macd_short,
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

    return {
        "rule": "EMA Stack (15M 9/21)",
        "description": "Short-term price structure aligned with trade direction",
        "long": long_pass,
        "short": short_pass,
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

    return {
        "rule": "Volume Surge (15M 1.2×)",
        "description": "Real buying/selling pressure backing the move",
        "long": surge,
        "short": surge,
        "value": f"Volume: {cur_vol:,.0f}  |  Avg: {avg_vol:,.0f}  |  Ratio: {ratio:.2f}×",
        "signal_hint": f"Current volume must be ≥ {CONFIG['volume_multiplier']}× the {CONFIG['volume_avg_period']}-candle average",
        "error": False,
    }


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

    # Convert numpy types to native Python types for JSON serialization
    for r in rules:
        r["long"] = bool(r["long"])
        r["short"] = bool(r["short"])
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

    # Get current price from rule 1 data (it fetches 4H)
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
        "current_price": current_price,
        "timestamp": datetime.now().isoformat(),
        "timestamp_display": datetime.now().strftime("%Y-%m-%d %H:%M:%S UTC"),
    }
