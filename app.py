"""
app.py - Crypto Trading Signal Dashboard
Run: python app.py
Then open: http://localhost:5000
"""

from flask import Flask, jsonify, render_template_string, request
from flask.json.provider import DefaultJSONProvider
from analyzer import analyze, calculate_trade_setup, SYMBOLS
from datetime import datetime
import threading
import time
import json
import os
import numpy as np

# ─── Data Directory ───────────────────────────────────────────────────────────
DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
os.makedirs(DATA_DIR, exist_ok=True)
SETTINGS_PATH = os.path.join(DATA_DIR, "settings.json")

DEFAULT_SETTINGS = {
    "account_balance": 1000.0,
    "risk_pct": 0.02,
    "max_leverage": 5,
}


def load_settings() -> dict:
    try:
        with open(SETTINGS_PATH, "r") as f:
            saved = json.load(f)
        return {**DEFAULT_SETTINGS, **saved}
    except (FileNotFoundError, json.JSONDecodeError):
        return DEFAULT_SETTINGS.copy()


def save_settings(settings: dict) -> None:
    with open(SETTINGS_PATH, "w") as f:
        json.dump(settings, f, indent=2)


# ─── Trade Journal Persistence ────────────────────────────────────────────────
TRADES_PATH = os.path.join(DATA_DIR, "trades.json")
SIGNALS_PATH = os.path.join(DATA_DIR, "signals.json")
trades_lock = threading.Lock()


def load_trades() -> list:
    try:
        with open(TRADES_PATH, "r") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return []


def save_trades(trades: list) -> None:
    with open(TRADES_PATH, "w") as f:
        json.dump(trades, f, indent=2)


def load_signals() -> list:
    try:
        with open(SIGNALS_PATH, "r") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return []


def save_signals(signals: list) -> None:
    with open(SIGNALS_PATH, "w") as f:
        json.dump(signals, f, indent=2)


class NumpyJSONProvider(DefaultJSONProvider):
    @staticmethod
    def default(o):
        if isinstance(o, np.integer):
            return int(o)
        if isinstance(o, np.floating):
            return float(o)
        if isinstance(o, np.bool_):
            return bool(o)
        if isinstance(o, np.ndarray):
            return o.tolist()
        return DefaultJSONProvider.default(o)


app = Flask(__name__)
app.json_provider_class = NumpyJSONProvider
app.json = NumpyJSONProvider(app)

# ─── Signal History (persisted to disk) ───────────────────────────────────────
signal_history = load_signals()
cache = {}
cache_lock = threading.Lock()
CACHE_TTL = 60  # seconds before re-fetching


def get_cached_analysis(symbol: str) -> dict:
    """Return cached analysis or fetch fresh if stale."""
    with cache_lock:
        entry = cache.get(symbol)
        now = time.time()
        if entry and (now - entry["fetched_at"]) < CACHE_TTL:
            return entry["data"]

    data = analyze(symbol)

    with cache_lock:
        cache[symbol] = {"data": data, "fetched_at": time.time()}

        # Log to history if it's a real signal
        if data["signal"] in ("BUY", "SELL"):
            signal_history.insert(0, {
                "symbol": data["symbol"],
                "signal": data["signal"],
                "price": data["current_price"],
                "timestamp": data["timestamp_display"],
                "confidence": data.get("confidence_score", 0),
            })
            # Keep only last 50 signals
            del signal_history[50:]
            save_signals(signal_history)

    return data


# ─── HTML Dashboard ────────────────────────────────────────────────────────────
DASHBOARD_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0"/>
  <title>Crypto Signal Dashboard</title>
  <style>
    :root {
      --bg: #0d1117;
      --surface: #161b22;
      --surface2: #21262d;
      --border: #30363d;
      --text: #e6edf3;
      --muted: #8b949e;
      --green: #3fb950;
      --green-bg: #0d2b12;
      --red: #f85149;
      --red-bg: #2d0d0a;
      --yellow: #d29922;
      --yellow-bg: #2b1d00;
      --blue: #58a6ff;
      --accent: #1f6feb;
    }

    * { box-sizing: border-box; margin: 0; padding: 0; }

    body {
      background: var(--bg);
      color: var(--text);
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, monospace;
      min-height: 100vh;
    }

    /* ── Header ── */
    header {
      background: var(--surface);
      border-bottom: 1px solid var(--border);
      padding: 16px 24px;
      display: flex;
      align-items: center;
      justify-content: space-between;
      flex-wrap: wrap;
      gap: 12px;
    }

    .logo {
      font-size: 18px;
      font-weight: 700;
      color: var(--blue);
      letter-spacing: 1px;
    }

    .logo span { color: var(--muted); font-weight: 400; font-size: 13px; margin-left: 10px; }

    .status-bar {
      display: flex;
      align-items: center;
      gap: 16px;
      font-size: 12px;
      color: var(--muted);
    }

    .dot {
      width: 8px; height: 8px;
      border-radius: 50%;
      background: var(--green);
      animation: pulse 2s infinite;
    }

    @keyframes pulse {
      0%, 100% { opacity: 1; }
      50% { opacity: 0.4; }
    }

    #countdown { color: var(--blue); font-weight: 600; }

    /* ── Layout ── */
    .container { max-width: 1400px; margin: 0 auto; padding: 24px; }

    /* ── Symbol Tabs ── */
    .tabs {
      display: flex;
      gap: 8px;
      flex-wrap: wrap;
      margin-bottom: 24px;
    }

    .tab {
      padding: 8px 18px;
      border-radius: 6px;
      border: 1px solid var(--border);
      background: var(--surface);
      color: var(--muted);
      cursor: pointer;
      font-size: 13px;
      font-weight: 600;
      transition: all 0.15s;
    }

    .tab:hover { border-color: var(--blue); color: var(--text); }
    .tab.active { background: var(--accent); border-color: var(--accent); color: #fff; }

    .tab .badge {
      display: inline-block;
      padding: 1px 6px;
      border-radius: 10px;
      font-size: 10px;
      margin-left: 6px;
      font-weight: 700;
    }

    .badge-buy { background: var(--green-bg); color: var(--green); }
    .badge-sell { background: var(--red-bg); color: var(--red); }
    .badge-wait { background: var(--surface2); color: var(--muted); }

    /* ── Main Grid ── */
    .main-grid {
      display: grid;
      grid-template-columns: 1fr 340px;
      gap: 20px;
    }

    @media (max-width: 900px) { .main-grid { grid-template-columns: 1fr; } }

    /* ── Signal Card ── */
    .signal-card {
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: 10px;
      padding: 28px;
      text-align: center;
      margin-bottom: 20px;
    }

    .signal-label {
      font-size: 11px;
      text-transform: uppercase;
      letter-spacing: 2px;
      color: var(--muted);
      margin-bottom: 12px;
    }

    .signal-badge {
      display: inline-block;
      font-size: 42px;
      font-weight: 900;
      padding: 16px 48px;
      border-radius: 12px;
      letter-spacing: 4px;
      margin: 8px 0;
    }

    .signal-badge.BUY  { background: var(--green-bg); color: var(--green); border: 2px solid var(--green); }
    .signal-badge.SELL { background: var(--red-bg);   color: var(--red);   border: 2px solid var(--red); }
    .signal-badge.WAIT { background: var(--surface2); color: var(--muted); border: 2px solid var(--border); }

    .signal-price {
      font-size: 26px;
      font-weight: 700;
      color: var(--text);
      margin-top: 12px;
    }

    .signal-price span { font-size: 13px; color: var(--muted); margin-right: 6px; }

    .signal-meta {
      font-size: 12px;
      color: var(--muted);
      margin-top: 8px;
    }

    .progress-label {
      font-size: 12px;
      color: var(--muted);
      margin: 16px 0 6px;
    }

    .progress-bar-wrap {
      background: var(--surface2);
      border-radius: 4px;
      height: 8px;
      overflow: hidden;
    }

    .progress-bar-fill {
      height: 100%;
      border-radius: 4px;
      transition: width 0.5s ease;
    }

    .fill-green  { background: var(--green); }
    .fill-red    { background: var(--red); }
    .fill-yellow { background: var(--yellow); }
    .fill-gray   { background: var(--muted); }

    /* ── Rules Panel ── */
    .rules-panel {
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: 10px;
      overflow: hidden;
    }

    .rules-header {
      padding: 16px 20px;
      border-bottom: 1px solid var(--border);
      font-size: 13px;
      font-weight: 600;
      color: var(--muted);
      text-transform: uppercase;
      letter-spacing: 1px;
    }

    .rule-row {
      padding: 14px 20px;
      border-bottom: 1px solid var(--border);
      display: flex;
      align-items: flex-start;
      gap: 14px;
      transition: background 0.1s;
    }

    .rule-row:last-child { border-bottom: none; }
    .rule-row:hover { background: var(--surface2); }

    .rule-icon {
      font-size: 20px;
      line-height: 1;
      margin-top: 2px;
      flex-shrink: 0;
    }

    .rule-name {
      font-size: 13px;
      font-weight: 600;
      color: var(--text);
    }

    .rule-desc {
      font-size: 11px;
      color: var(--muted);
      margin-top: 2px;
    }

    .rule-value {
      font-size: 11px;
      color: var(--blue);
      margin-top: 4px;
      font-family: monospace;
    }

    .rule-pills {
      display: flex;
      gap: 6px;
      margin-top: 5px;
    }

    .pill {
      font-size: 10px;
      font-weight: 700;
      padding: 2px 8px;
      border-radius: 10px;
    }

    .pill-pass-long  { background: var(--green-bg); color: var(--green); }
    .pill-fail-long  { background: var(--surface2); color: var(--muted); }
    .pill-pass-short { background: var(--red-bg); color: var(--red); }
    .pill-fail-short { background: var(--surface2); color: var(--muted); }

    /* ── Right Column ── */
    .right-col { display: flex; flex-direction: column; gap: 20px; }

    .panel {
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: 10px;
      overflow: hidden;
    }

    .panel-header {
      padding: 14px 18px;
      border-bottom: 1px solid var(--border);
      font-size: 12px;
      font-weight: 600;
      color: var(--muted);
      text-transform: uppercase;
      letter-spacing: 1px;
      display: flex;
      justify-content: space-between;
    }

    /* ── Framework Info ── */
    .framework-row {
      padding: 10px 18px;
      border-bottom: 1px solid var(--border);
      font-size: 12px;
    }

    .framework-row:last-child { border-bottom: none; }

    .fw-label { color: var(--muted); margin-bottom: 2px; }
    .fw-value { color: var(--text); font-weight: 500; }

    /* ── History ── */
    .history-row {
      padding: 10px 18px;
      border-bottom: 1px solid var(--border);
      display: flex;
      justify-content: space-between;
      align-items: center;
      font-size: 12px;
    }

    .history-row:last-child { border-bottom: none; }

    .hist-sym { font-weight: 600; color: var(--text); }
    .hist-time { color: var(--muted); font-size: 11px; margin-top: 2px; }
    .hist-price { color: var(--blue); font-family: monospace; }

    .sig-chip {
      padding: 2px 10px;
      border-radius: 8px;
      font-weight: 700;
      font-size: 11px;
    }

    .sig-chip.BUY  { background: var(--green-bg); color: var(--green); }
    .sig-chip.SELL { background: var(--red-bg);   color: var(--red); }

    .no-signals {
      padding: 24px 18px;
      text-align: center;
      color: var(--muted);
      font-size: 12px;
    }

    /* ── Loading spinner ── */
    .loading {
      display: flex;
      align-items: center;
      justify-content: center;
      padding: 48px;
      color: var(--muted);
      font-size: 14px;
      gap: 12px;
    }

    .spinner {
      width: 20px; height: 20px;
      border: 3px solid var(--border);
      border-top-color: var(--blue);
      border-radius: 50%;
      animation: spin 0.8s linear infinite;
    }

    @keyframes spin { to { transform: rotate(360deg); } }

    /* ── Per-rule strength bar ── */
    .rule-strength-bar {
      height: 4px;
      border-radius: 2px;
      background: var(--surface2);
      margin-top: 6px;
      overflow: hidden;
    }

    .rule-strength-fill {
      height: 100%;
      border-radius: 2px;
      transition: width 0.4s ease;
    }

    /* ── Signal Forming Banner ── */
    @keyframes pulseBanner {
      0%, 100% { opacity: 1; }
      50% { opacity: 0.7; }
    }

    .forming-banner {
      background: var(--yellow-bg);
      border: 1px solid var(--yellow);
      color: var(--yellow);
      padding: 12px;
      border-radius: 8px;
      margin-bottom: 20px;
      font-size: 14px;
      font-weight: 600;
      animation: pulseBanner 2s ease-in-out infinite;
    }

    /* ── Refresh Mode Toggle ── */
    .refresh-toggle {
      display: inline-flex;
      gap: 0;
      border-radius: 6px;
      overflow: hidden;
      border: 1px solid var(--border);
    }

    .refresh-toggle-btn {
      background: var(--surface2);
      border: none;
      color: var(--muted);
      padding: 5px 12px;
      cursor: pointer;
      font-size: 11px;
      font-weight: 600;
      transition: all 0.15s;
    }

    .refresh-toggle-btn:hover {
      color: var(--text);
    }

    .refresh-toggle-btn.active {
      background: var(--accent);
      color: #fff;
    }

    /* ── Trade Setup Card ── */
    .trade-setup-card {
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: 10px;
      overflow: hidden;
      margin-top: 20px;
    }

    .trade-setup-header {
      padding: 14px 18px;
      border-bottom: 1px solid var(--border);
      font-size: 12px;
      font-weight: 600;
      color: var(--muted);
      text-transform: uppercase;
      letter-spacing: 1px;
      display: flex;
      justify-content: space-between;
      align-items: center;
    }

    .trade-setup-row {
      padding: 8px 18px;
      border-bottom: 1px solid var(--border);
      display: flex;
      justify-content: space-between;
      align-items: center;
      font-size: 12px;
    }

    .trade-setup-row:last-child { border-bottom: none; }

    .ts-label { color: var(--muted); }
    .ts-value { color: var(--text); font-weight: 500; font-family: monospace; }
    .ts-pct-red { color: var(--red); font-size: 11px; margin-left: 4px; }
    .ts-pct-green { color: var(--green); font-size: 11px; margin-left: 4px; }

    .direction-badge {
      display: inline-block;
      padding: 4px 14px;
      border-radius: 6px;
      font-weight: 700;
      font-size: 13px;
      letter-spacing: 1px;
    }

    .direction-badge.LONG { background: var(--green-bg); color: var(--green); border: 1px solid var(--green); }
    .direction-badge.SHORT { background: var(--red-bg); color: var(--red); border: 1px solid var(--red); }

    .leverage-badge {
      display: inline-block;
      padding: 3px 10px;
      border-radius: 6px;
      font-weight: 700;
      font-size: 12px;
      background: var(--yellow-bg);
      color: var(--yellow);
      border: 1px solid var(--yellow);
    }

    .rr-value { color: var(--blue); font-size: 11px; margin-left: 6px; }

    .trade-setup-muted {
      padding: 24px 18px;
      text-align: center;
      color: var(--muted);
      font-size: 12px;
    }

    .btn-copy-setup {
      background: var(--accent);
      border: none;
      color: #fff;
      padding: 6px 14px;
      border-radius: 6px;
      cursor: pointer;
      font-size: 11px;
      font-weight: 600;
      transition: opacity 0.15s;
    }

    .btn-copy-setup:hover { opacity: 0.85; }

    .btn-log-trade {
      background: var(--green);
      border: none;
      color: #fff;
      padding: 6px 14px;
      border-radius: 6px;
      cursor: pointer;
      font-size: 11px;
      font-weight: 600;
      transition: opacity 0.15s;
      margin-left: 6px;
    }

    .btn-log-trade:hover { opacity: 0.85; }

    /* ── Trade Journal Section ── */
    .journal-section {
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: 10px;
      overflow: hidden;
      margin-top: 20px;
    }

    .journal-header {
      padding: 14px 18px;
      border-bottom: 1px solid var(--border);
      font-size: 12px;
      font-weight: 600;
      color: var(--muted);
      text-transform: uppercase;
      letter-spacing: 1px;
    }

    .journal-tabs {
      display: flex;
      gap: 0;
      border-bottom: 1px solid var(--border);
    }

    .journal-tab {
      padding: 10px 20px;
      border: none;
      background: none;
      color: var(--muted);
      cursor: pointer;
      font-size: 12px;
      font-weight: 600;
      border-bottom: 2px solid transparent;
      transition: all 0.15s;
    }

    .journal-tab:hover { color: var(--text); }

    .journal-tab.active {
      color: var(--blue);
      border-bottom-color: var(--blue);
    }

    .journal-tab-content {
      display: none;
    }

    .journal-tab-content.active {
      display: block;
    }

    .journal-table {
      width: 100%;
      border-collapse: collapse;
      font-size: 12px;
    }

    .journal-table th {
      text-align: left;
      padding: 10px 14px;
      color: var(--muted);
      font-weight: 600;
      font-size: 11px;
      text-transform: uppercase;
      letter-spacing: 0.5px;
      border-bottom: 1px solid var(--border);
    }

    .journal-table td {
      padding: 10px 14px;
      border-bottom: 1px solid var(--border);
      color: var(--text);
    }

    .journal-table tr:last-child td { border-bottom: none; }

    .journal-table tr:hover { background: var(--surface2); }

    .pnl-green { color: var(--green); font-weight: 600; }
    .pnl-red { color: var(--red); font-weight: 600; }

    .btn-close-trade {
      background: var(--red);
      border: none;
      color: #fff;
      padding: 4px 10px;
      border-radius: 4px;
      cursor: pointer;
      font-size: 10px;
      font-weight: 600;
    }

    .btn-close-trade:hover { opacity: 0.85; }

    .close-trade-form {
      display: inline-flex;
      align-items: center;
      gap: 6px;
    }

    .close-trade-input {
      width: 100px;
      padding: 4px 8px;
      border-radius: 4px;
      border: 1px solid var(--border);
      background: var(--surface2);
      color: var(--text);
      font-size: 11px;
      font-family: monospace;
      outline: none;
    }

    .close-trade-input:focus { border-color: var(--accent); }

    .btn-confirm-close {
      background: var(--red);
      border: none;
      color: #fff;
      padding: 4px 10px;
      border-radius: 4px;
      cursor: pointer;
      font-size: 10px;
      font-weight: 600;
    }

    .btn-confirm-close:hover { opacity: 0.85; }

    .btn-cancel-close {
      background: var(--surface2);
      border: 1px solid var(--border);
      color: var(--muted);
      padding: 4px 10px;
      border-radius: 4px;
      cursor: pointer;
      font-size: 10px;
      font-weight: 600;
    }

    .btn-cancel-close:hover { color: var(--text); }

    .journal-empty {
      padding: 24px 18px;
      text-align: center;
      color: var(--muted);
      font-size: 12px;
    }

    .stats-grid {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 12px;
      padding: 16px;
    }

    .stat-card {
      background: var(--surface2);
      border-radius: 8px;
      padding: 16px;
    }

    .stat-card-label {
      font-size: 11px;
      color: var(--muted);
      text-transform: uppercase;
      letter-spacing: 0.5px;
      margin-bottom: 6px;
    }

    .stat-card-value {
      font-size: 22px;
      font-weight: 700;
      color: var(--text);
      font-family: monospace;
    }

    /* ── Settings Panel ── */
    .settings-row {
      padding: 10px 18px;
      border-bottom: 1px solid var(--border);
      font-size: 12px;
    }

    .settings-row:last-child { border-bottom: none; }

    .settings-label {
      color: var(--muted);
      margin-bottom: 4px;
      font-size: 11px;
    }

    .settings-input {
      width: 100%;
      padding: 6px 10px;
      border-radius: 6px;
      border: 1px solid var(--border);
      background: var(--surface2);
      color: var(--text);
      font-size: 13px;
      font-family: monospace;
      outline: none;
      transition: border-color 0.15s;
    }

    .settings-input:focus { border-color: var(--accent); }

    .settings-saved {
      font-size: 10px;
      color: var(--green);
      opacity: 0;
      transition: opacity 0.2s;
      margin-left: 8px;
    }

    .settings-saved.show { opacity: 1; }

    /* ── Trading Guide (Collapsible) ── */
    .guide-toggle {
      width: 100%;
      background: none;
      border: none;
      padding: 14px 18px;
      border-bottom: 1px solid var(--border);
      font-size: 12px;
      font-weight: 600;
      color: var(--muted);
      text-transform: uppercase;
      letter-spacing: 1px;
      cursor: pointer;
      display: flex;
      justify-content: space-between;
      align-items: center;
      text-align: left;
    }

    .guide-toggle:hover { color: var(--text); }

    .guide-arrow {
      transition: transform 0.2s;
      font-size: 10px;
    }

    .guide-arrow.open { transform: rotate(180deg); }

    .guide-content {
      max-height: 0;
      overflow: hidden;
      transition: max-height 0.3s ease;
    }

    .guide-content.open {
      max-height: 2000px;
    }

    .guide-section {
      padding: 10px 18px;
      border-bottom: 1px solid var(--border);
    }

    .guide-section:last-child { border-bottom: none; }

    .guide-section-title {
      font-size: 12px;
      font-weight: 700;
      color: var(--text);
      margin-bottom: 6px;
    }

    .guide-section p,
    .guide-section li {
      font-size: 11px;
      color: var(--muted);
      line-height: 1.5;
      margin-bottom: 4px;
    }

    .guide-section ul,
    .guide-section ol {
      padding-left: 16px;
      margin: 4px 0;
    }

    .guide-section ol li { margin-bottom: 3px; }

    .conf-dot {
      display: inline-block;
      width: 8px;
      height: 8px;
      border-radius: 50%;
      margin-right: 4px;
    }

    .conf-dot.green { background: var(--green); }
    .conf-dot.yellow { background: var(--yellow); }
    .conf-dot.gray { background: var(--muted); }
  </style>
</head>
<body>

<header>
  <div class="logo">
    ◈ CryptoSignal
    <span>5-Rule Confluence Framework</span>
  </div>
  <div class="status-bar">
    <div class="dot"></div>
    <span>Live via ByBit</span>
    <span>|</span>
    <span>Refresh in <strong id="countdown">60</strong>s</span>
    <div class="refresh-toggle">
      <button id="btn-polling" class="refresh-toggle-btn active" onclick="setRefreshMode('polling')">Polling (60s)</button>
      <button id="btn-realtime" class="refresh-toggle-btn" onclick="setRefreshMode('realtime')">Real-Time (10s)</button>
    </div>
    <button onclick="loadSymbol(activeSymbol, true)" style="
      background: var(--accent); border: none; color: #fff;
      padding: 6px 14px; border-radius: 6px; cursor: pointer; font-size: 12px;">
      ↻ Refresh Now
    </button>
    <button id="sound-toggle" onclick="toggleSound()" style="
      background: var(--surface2); border: 1px solid var(--border); color: var(--muted);
      padding: 5px 10px; border-radius: 6px; cursor: pointer; font-size: 16px;"
      title="Toggle audio alerts">🔇</button>
  </div>
</header>

<div class="container">

  <!-- Symbol Tabs -->
  <div class="tabs" id="tabs"></div>

  <!-- Main Content -->
  <div id="content">
    <div class="loading">
      <div class="spinner"></div>
      Loading signal data…
    </div>
  </div>

</div>

<script>
const SYMBOLS = {{ symbols | tojson }};
let activeSymbol = SYMBOLS[0];
let allData = {};
let countdownVal = 60;
let countdownTimer = null;
let refreshMode = 'polling'; // 'polling' (60s) or 'realtime' (10s)
let soundEnabled = false;
let lastNotifiedState = {}; // { symbol: { signal, forming } }

// ── Notification permission ────────────────────────────────────────────────
if ('Notification' in window) {
  Notification.requestPermission();
}

// ── Audio alert ────────────────────────────────────────────────────────────
function playBeep() {
  const ctx = new (window.AudioContext || window.webkitAudioContext)();
  const osc = ctx.createOscillator();
  const gain = ctx.createGain();
  osc.connect(gain);
  gain.connect(ctx.destination);
  osc.frequency.value = 800;
  gain.gain.value = 0.3;
  osc.start();
  osc.stop(ctx.currentTime + 0.15);
}

function toggleSound() {
  soundEnabled = !soundEnabled;
  const btn = document.getElementById('sound-toggle');
  if (btn) {
    btn.textContent = soundEnabled ? '🔊' : '🔇';
    btn.style.color = soundEnabled ? 'var(--green)' : 'var(--muted)';
  }
}

// ── Send browser notification (deduped per symbol) ─────────────────────────
function sendNotification(title, body) {
  if (!('Notification' in window)) return;
  if (Notification.permission !== 'granted') return;
  new Notification(title, { body });
}

function checkAndNotify(data) {
  const sym = data.symbol;
  const prev = lastNotifiedState[sym] || {};
  const signal = data.signal;
  const forming = !!data.forming;

  let signalChanged = false;
  let formingChanged = false;

  if ((signal === 'BUY' || signal === 'SELL') && prev.signal !== signal) {
    signalChanged = true;
    const confScore = data.confidence_score != null ? data.confidence_score.toFixed(0) : '0';
    const confLabel = data.confidence_label || '';
    sendNotification(
      `${sym}: ${signal} Signal!`,
      `Confidence: ${confScore}% ${confLabel}`
    );
  }

  if (forming && !prev.forming) {
    formingChanged = true;
    const dir = data.forming_direction || '—';
    const rulesMet = dir === 'LONG' ? data.long_rules_met : data.short_rules_met;
    sendNotification(
      `${sym}: ${dir} signal forming`,
      `${rulesMet}/${data.total_rules} rules passing`
    );
  }

  if (signalChanged && soundEnabled) {
    playBeep();
  }

  lastNotifiedState[sym] = { signal, forming };
}

function getRefreshInterval() {
  return refreshMode === 'realtime' ? 10 : 60;
}

function setRefreshMode(mode) {
  refreshMode = mode;
  document.getElementById('btn-polling').classList.toggle('active', mode === 'polling');
  document.getElementById('btn-realtime').classList.toggle('active', mode === 'realtime');
  resetCountdown();
}

// ── Fetch signal for a symbol ──────────────────────────────────────────────
async function fetchSignal(symbol) {
  const res = await fetch(`/api/analyze?symbol=${encodeURIComponent(symbol)}`);
  if (!res.ok) throw new Error("Fetch failed");
  return res.json();
}

// ── Load all symbols (for tab badges) ─────────────────────────────────────
async function loadAllSymbols() {
  const promises = SYMBOLS.map(s => fetchSignal(s).then(d => { allData[s] = d; }).catch(() => {}));
  await Promise.all(promises);
  renderTabs();
}

// ── Load a specific symbol ─────────────────────────────────────────────────
async function loadSymbol(symbol, force = false) {
  activeSymbol = symbol;
  renderTabs();
  document.getElementById("content").innerHTML = `
    <div class="loading"><div class="spinner"></div>Analyzing ${symbol}…</div>`;

  try {
    const url = `/api/analyze?symbol=${encodeURIComponent(symbol)}${force ? "&force=1" : ""}`;
    const res = await fetch(url);
    if (!res.ok) throw new Error("Fetch failed");
    const data = await res.json();
    allData[symbol] = data;
    renderTabs();
    renderDashboard(data);
    resetCountdown();
  } catch (e) {
    document.getElementById("content").innerHTML =
      `<div class="loading" style="color:var(--red)">⚠ Failed to load data. Check your connection.</div>`;
  }
}

// ── Render symbol tabs with signal badges ─────────────────────────────────
function renderTabs() {
  const tabsEl = document.getElementById("tabs");
  tabsEl.innerHTML = SYMBOLS.map(sym => {
    const d = allData[sym];
    const sig = d ? d.signal : "…";
    const badgeClass = sig === "BUY" ? "badge-buy" : sig === "SELL" ? "badge-sell" : "badge-wait";
    const active = sym === activeSymbol ? "active" : "";
    const pair = sym.replace("/USDT", "");
    return `<div class="tab ${active}" onclick="loadSymbol('${sym}')">
      ${pair}
      <span class="badge ${badgeClass}">${sig}</span>
    </div>`;
  }).join("");
}

// ── Render the main dashboard ──────────────────────────────────────────────
function renderDashboard(data) {
  const sigClass = data.signal;
  const longPct = Math.round((data.long_rules_met / data.total_rules) * 100);
  const shortPct = Math.round((data.short_rules_met / data.total_rules) * 100);

  const confScore = data.confidence_score != null ? data.confidence_score : 0;
  const confLabel = data.confidence_label || "";
  const confColorMap = { green: "fill-green", yellow: "fill-yellow", gray: "fill-gray" };
  const confFill = confColorMap[data.confidence_color] || "fill-gray";

  const priceDisplay = data.current_price
    ? `$${Number(data.current_price).toLocaleString("en-US", {minimumFractionDigits: 2, maximumFractionDigits: 6})}`
    : "—";

  // Rules HTML
  const rulesHtml = data.rules.map(r => {
    const icon = r.long && r.short ? "✅" : r.long ? "🟢" : r.short ? "🔴" : "⬜";
    const longPill = `<span class="pill ${r.long ? 'pill-pass-long' : 'pill-fail-long'}">${r.long ? "✓ LONG" : "✗ LONG"}</span>`;
    const shortPill = `<span class="pill ${r.short ? 'pill-pass-short' : 'pill-fail-short'}">${r.short ? "✓ SHORT" : "✗ SHORT"}</span>`;
    const strength = r.strength != null ? r.strength : 0;
    const strengthPct = Math.round(strength * 100);
    const strengthColor = strength > 0.7 ? 'var(--green)' : strength > 0.4 ? 'var(--yellow)' : 'var(--muted)';
    return `
      <div class="rule-row">
        <div class="rule-icon">${icon}</div>
        <div style="flex:1">
          <div class="rule-name">${r.rule}</div>
          <div class="rule-desc">${r.description || ""}</div>
          <div class="rule-value">${r.value || ""}</div>
          <div class="rule-pills">${longPill}${shortPill}</div>
          <div class="rule-strength-bar">
            <div class="rule-strength-fill" style="width:${strengthPct}%;background:${strengthColor}"></div>
          </div>
        </div>
      </div>`;
  }).join("");

  // History HTML
  const historyHtml = window._history && window._history.length
    ? window._history.slice(0, 10).map(h => `
        <div class="history-row">
          <div>
            <div class="hist-sym">${h.symbol.replace("/USDT","")}</div>
            <div class="hist-time">${h.timestamp}</div>
          </div>
          <div style="text-align:right">
            <div><span class="sig-chip ${h.signal}">${h.signal}</span></div>
            <div class="hist-price">${h.price ? "$" + Number(h.price).toLocaleString("en-US", {minimumFractionDigits:2, maximumFractionDigits:6}) : "—"}</div>
          </div>
        </div>`).join("")
    : `<div class="no-signals">No signals fired yet.<br>Signals appear here when all 5 rules pass.</div>`;

  const formingBanner = data.forming
    ? `<div class="forming-banner">${data.symbol}: ${data.forming_direction || '—'} signal forming — ${
        data.forming_direction === 'LONG' ? data.long_rules_met : data.short_rules_met
      }/${data.total_rules} rules passing</div>`
    : '';

  document.getElementById("content").innerHTML = `
    ${formingBanner}
    <div class="main-grid">

      <!-- Left Column -->
      <div>
        <!-- Signal Card -->
        <div class="signal-card">
          <div class="signal-label">${data.symbol} · ${data.timestamp_display}</div>
          <div class="signal-badge ${sigClass}">${data.signal}</div>
          <div class="signal-price"><span>Price</span>${priceDisplay}</div>
          <div class="signal-meta">
            ${data.long_rules_met}/${data.total_rules} long rules  ·
            ${data.short_rules_met}/${data.total_rules} short rules
          </div>
          <div class="progress-label">Confidence: ${confScore.toFixed(1)}% ${confLabel}</div>
          <div class="progress-bar-wrap">
            <div class="progress-bar-fill ${confFill}" style="width:${confScore}%"></div>
          </div>
        </div>

        <!-- Rules Panel -->
        <div class="rules-panel">
          <div class="rules-header">📋 Rule Checklist — All 5 must pass</div>
          ${rulesHtml}
        </div>

        <!-- Trade Setup Card -->
        <div class="trade-setup-card" id="trade-setup-card">
          <div class="trade-setup-header">
            <span>📐 Trade Setup</span>
            <span id="trade-setup-actions"></span>
          </div>
          <div id="trade-setup-body">
            <div class="trade-setup-muted">Loading trade setup...</div>
          </div>
        </div>
      </div>

      <!-- Right Column -->
      <div class="right-col">

        <!-- Settings Panel -->
        <div class="panel" id="settings-panel">
          <div class="panel-header">
            <span>⚙ Account Settings</span>
            <span class="settings-saved" id="settings-saved-indicator">Saved</span>
          </div>
          <div class="settings-row">
            <div class="settings-label">Account Balance (USDT)</div>
            <input type="number" class="settings-input" id="setting-balance" min="0" step="10" placeholder="1000">
          </div>
          <div class="settings-row">
            <div class="settings-label">Risk % per Trade</div>
            <input type="number" class="settings-input" id="setting-risk" min="0.5" max="10" step="0.5" placeholder="2">
          </div>
          <div class="settings-row">
            <div class="settings-label">Max Leverage</div>
            <input type="number" class="settings-input" id="setting-leverage" min="2" max="10" step="1" placeholder="5">
          </div>
        </div>

        <!-- Framework Info -->
        <div class="panel">
          <div class="panel-header">⚙ Framework Settings</div>
          <div class="framework-row">
            <div class="fw-label">Strategy</div>
            <div class="fw-value">Multi-Timeframe Confluence</div>
          </div>
          <div class="framework-row">
            <div class="fw-label">Timeframes</div>
            <div class="fw-value">4H · 1H · 15M</div>
          </div>
          <div class="framework-row">
            <div class="fw-label">Signal Logic</div>
            <div class="fw-value">ALL 5 rules must pass</div>
          </div>
          <div class="framework-row">
            <div class="fw-label">Target Trades/Day</div>
            <div class="fw-value">1–2 high-quality setups</div>
          </div>
          <div class="framework-row">
            <div class="fw-label">Data Source</div>
            <div class="fw-value">ByBit (Free API)</div>
          </div>
          <div class="framework-row">
            <div class="fw-label">Refresh Rate</div>
            <div class="fw-value">Every 60 seconds</div>
          </div>
        </div>

        <!-- Signal History -->
        <div class="panel">
          <div class="panel-header">
            <span>🔔 Signal History</span>
            <span style="color:var(--blue)">${window._history ? window._history.length : 0} fired</span>
          </div>
          ${historyHtml}
        </div>

        <!-- Trading Guide (Collapsible) -->
        <div class="panel">
          <button class="guide-toggle" onclick="toggleGuide()">
            <span>📖 Trading Guide</span>
            <span class="guide-arrow" id="guide-arrow">▼</span>
          </button>
          <div class="guide-content" id="guide-content">
            <div class="guide-section">
              <div class="guide-section-title">How the 5-Rule Framework Works</div>
              <p>The framework uses a confluence-based approach: a signal only fires when ALL 5 independent technical rules agree on direction. Each rule analyzes a different aspect of price action (trend, momentum, volume, structure, multi-timeframe alignment). This high bar filters out noise and produces fewer but higher-quality setups. The more rules that align strongly, the higher the confidence score.</p>
            </div>
            <div class="guide-section">
              <div class="guide-section-title">Signal Confidence Levels</div>
              <ul>
                <li><span class="conf-dot green"></span><strong>Strong (70-100%)</strong> — Most rules show strong individual readings. High-probability setup.</li>
                <li><span class="conf-dot yellow"></span><strong>Medium (40-69%)</strong> — Rules pass but some are borderline. Consider smaller position size.</li>
                <li><span class="conf-dot gray"></span><strong>Weak (0-39%)</strong> — Rules barely passing. Use extreme caution or skip.</li>
              </ul>
            </div>
            <div class="guide-section">
              <div class="guide-section-title">Reading the Trade Setup</div>
              <ul>
                <li><strong>Direction</strong> — LONG (buy, expect price to rise) or SHORT (sell, expect price to fall).</li>
                <li><strong>Entry Price</strong> — Current market price at signal time.</li>
                <li><strong>Stop Loss</strong> — Exit price if the trade goes against you. The % shows distance from entry.</li>
                <li><strong>TP1/TP2/TP3</strong> — Take-profit targets at increasing distances. Scale out at each level.</li>
                <li><strong>R:R (Risk-to-Reward)</strong> — How much you gain per unit risked. 1:2 means you gain $2 for every $1 risked.</li>
                <li><strong>Leverage</strong> — Suggested leverage based on stop-loss distance and your max setting.</li>
                <li><strong>Position Size</strong> — How much to buy/sell, calculated from your balance and risk %.</li>
                <li><strong>Risk Amount</strong> — The dollar amount you stand to lose if stopped out.</li>
              </ul>
            </div>
            <div class="guide-section">
              <div class="guide-section-title">How to Place This Trade on ByBit</div>
              <ol>
                <li>Open ByBit and navigate to <strong>Derivatives > USDT Perpetual</strong>.</li>
                <li>Select the trading pair (e.g., BTC/USDT) from the pair list.</li>
                <li>Set your leverage to match the suggested leverage shown in the trade setup.</li>
                <li>Choose <strong>Long</strong> or <strong>Short</strong> based on the Direction field.</li>
                <li>Enter the position size (in coins or USDT) from the trade setup.</li>
                <li>Set a <strong>Stop Loss</strong> order at the displayed SL price, and <strong>Take Profit</strong> orders at TP1, TP2, and TP3.</li>
                <li>Review all details, confirm the order, and monitor your position.</li>
              </ol>
            </div>
            <div class="guide-section">
              <div class="guide-section-title">Risk Management</div>
              <ul>
                <li>Never risk more than 2% of your account on a single trade.</li>
                <li>Always use a stop loss — no exceptions.</li>
                <li>Scale out at take-profit levels: close 1/3 at TP1, 1/3 at TP2, and the final 1/3 at TP3.</li>
                <li>Move your stop loss to breakeven after TP1 is hit.</li>
                <li>Do not over-leverage. The suggested leverage already accounts for the stop-loss distance.</li>
                <li>If a signal has weak confidence, consider reducing position size by 50% or skipping entirely.</li>
              </ul>
            </div>
          </div>
        </div>

      </div>
    </div>

    <!-- Trade Journal Section -->
    <div class="journal-section" id="journal-section">
      <div class="journal-header">📓 Trade Journal</div>
      <div class="journal-tabs">
        <button class="journal-tab active" onclick="switchJournalTab('open')" id="jtab-open">Open Trades</button>
        <button class="journal-tab" onclick="switchJournalTab('closed')" id="jtab-closed">Closed Trades</button>
        <button class="journal-tab" onclick="switchJournalTab('stats')" id="jtab-stats">Stats</button>
      </div>
      <div class="journal-tab-content active" id="journal-open"></div>
      <div class="journal-tab-content" id="journal-closed"></div>
      <div class="journal-tab-content" id="journal-stats"></div>
    </div>`;

  checkAndNotify(data);
  fetchTradeSetup(data.symbol, data.signal);
  attachSettingsListeners();
  fetchJournal();
}

// ── Trade Setup ────────────────────────────────────────────────────────────
let lastTradeSetup = null;

function fmtPrice(v) {
  if (v == null) return "—";
  return "$" + Number(v).toLocaleString("en-US", {minimumFractionDigits: 2, maximumFractionDigits: 6});
}

async function fetchTradeSetup(symbol, signal) {
  const body = document.getElementById("trade-setup-body");
  const actions = document.getElementById("trade-setup-actions");
  if (!body) return;

  if (signal === "WAIT") {
    lastTradeSetup = null;
    if (actions) actions.innerHTML = "";
    body.innerHTML = `<div class="trade-setup-muted">No active signal — trade setup available when signal fires.</div>`;
    return;
  }

  try {
    const res = await fetch(`/api/trade-setup?symbol=${encodeURIComponent(symbol)}`);
    const data = await res.json();

    if (data.error) {
      lastTradeSetup = null;
      if (actions) actions.innerHTML = "";
      body.innerHTML = `<div class="trade-setup-muted">No active signal — trade setup available when signal fires.</div>`;
      return;
    }

    lastTradeSetup = { ...data, symbol };

    if (actions) {
      actions.innerHTML = `<button class="btn-copy-setup" onclick="copyTradeSetup()">Copy Setup</button><button class="btn-log-trade" onclick="logTrade()">Log This Trade</button>`;
    }

    body.innerHTML = `
      <div class="trade-setup-row">
        <span class="ts-label">Direction</span>
        <span><span class="direction-badge ${data.direction}">${data.direction}</span></span>
      </div>
      <div class="trade-setup-row">
        <span class="ts-label">Entry Price</span>
        <span class="ts-value">${fmtPrice(data.entry_price)}</span>
      </div>
      <div class="trade-setup-row">
        <span class="ts-label">Stop Loss</span>
        <span class="ts-value">${fmtPrice(data.stop_loss)}<span class="ts-pct-red">(${Number(data.sl_pct).toFixed(2)}%)</span></span>
      </div>
      <div class="trade-setup-row">
        <span class="ts-label">TP1</span>
        <span class="ts-value">${fmtPrice(data.tp1)}<span class="ts-pct-green">(+${Number(data.tp1_pct).toFixed(2)}%)</span><span class="rr-value">R:R 1:${Number(data.rr1).toFixed(1)}</span></span>
      </div>
      <div class="trade-setup-row">
        <span class="ts-label">TP2</span>
        <span class="ts-value">${fmtPrice(data.tp2)}<span class="ts-pct-green">(+${Number(data.tp2_pct).toFixed(2)}%)</span><span class="rr-value">R:R 1:${Number(data.rr2).toFixed(1)}</span></span>
      </div>
      <div class="trade-setup-row">
        <span class="ts-label">TP3</span>
        <span class="ts-value">${fmtPrice(data.tp3)}<span class="ts-pct-green">(+${Number(data.tp3_pct).toFixed(2)}%)</span><span class="rr-value">R:R 1:${Number(data.rr3).toFixed(1)}</span></span>
      </div>
      <div class="trade-setup-row">
        <span class="ts-label">Leverage</span>
        <span><span class="leverage-badge">${data.leverage}x</span></span>
      </div>
      <div class="trade-setup-row">
        <span class="ts-label">Position Size</span>
        <span class="ts-value">${Number(data.position_size_coin).toFixed(6)} ${symbol.split("/")[0]} (${fmtPrice(data.position_size_usdt)})</span>
      </div>
      <div class="trade-setup-row">
        <span class="ts-label">Risk Amount</span>
        <span class="ts-value">${fmtPrice(data.risk_amount)}</span>
      </div>
      <div class="trade-setup-row">
        <span class="ts-label">Confidence</span>
        <span class="ts-value">${Number(data.confidence_score).toFixed(0)}% (${data.confidence_label})</span>
      </div>`;
  } catch (e) {
    lastTradeSetup = null;
    if (actions) actions.innerHTML = "";
    body.innerHTML = `<div class="trade-setup-muted" style="color:var(--red)">Failed to load trade setup.</div>`;
  }
}

async function copyTradeSetup() {
  if (!lastTradeSetup) return;
  const d = lastTradeSetup;
  const ts = d.timestamp || "—";
  const riskPctDisplay = window._settingsCache ? (window._settingsCache.risk_pct * 100).toFixed(0) + "%" : "2%";
  const text = [
    "=== TRADE SETUP ===",
    `Pair:       ${d.symbol}`,
    `Direction:  ${d.direction}`,
    `Entry:      ${fmtPrice(d.entry_price)}`,
    `Stop Loss:  ${fmtPrice(d.stop_loss)} (${Number(d.sl_pct).toFixed(2)}%)`,
    `TP1:        ${fmtPrice(d.tp1)} (+${Number(d.tp1_pct).toFixed(2)}%)`,
    `TP2:        ${fmtPrice(d.tp2)} (+${Number(d.tp2_pct).toFixed(2)}%)`,
    `TP3:        ${fmtPrice(d.tp3)} (+${Number(d.tp3_pct).toFixed(2)}%)`,
    `Leverage:   ${d.leverage}x`,
    `Size:       ${Number(d.position_size_coin).toFixed(6)} ${d.symbol.split("/")[0]} (${fmtPrice(d.position_size_usdt)})`,
    `Risk:       ${riskPctDisplay} of balance`,
    `Confidence: ${Number(d.confidence_score).toFixed(0)}% (${d.confidence_label})`,
    `Signal:     ${ts}`,
    "===================",
  ].join("\\n");

  try {
    await navigator.clipboard.writeText(text);
    const btn = document.querySelector(".btn-copy-setup");
    if (btn) {
      const orig = btn.textContent;
      btn.textContent = "Copied!";
      setTimeout(() => { btn.textContent = orig; }, 1500);
    }
  } catch (e) {
    // fallback
  }
}

// ── Trade Journal ──────────────────────────────────────────────────────────
let journalActiveTab = 'open';

async function logTrade() {
  if (!lastTradeSetup) return;
  const d = lastTradeSetup;
  const payload = {
    symbol: d.symbol,
    direction: d.direction,
    entry_price: d.entry_price,
    stop_loss: d.stop_loss,
    tp1: d.tp1,
    tp2: d.tp2,
    tp3: d.tp3,
    leverage: d.leverage,
    position_size_usdt: d.position_size_usdt,
    position_size_coin: d.position_size_coin,
    risk_pct: d.risk_pct || (window._settingsCache ? window._settingsCache.risk_pct : 0.02),
    risk_amount: d.risk_amount,
    confidence_score: d.confidence_score,
    notes: "",
  };

  try {
    const res = await fetch("/api/trades", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    if (!res.ok) throw new Error("Failed to log trade");
    const btn = document.querySelector(".btn-log-trade");
    if (btn) {
      const orig = btn.textContent;
      btn.textContent = "Logged!";
      btn.style.opacity = "0.7";
      setTimeout(() => { btn.textContent = orig; btn.style.opacity = "1"; }, 1500);
    }
    fetchJournal();
  } catch (e) {
    const btn = document.querySelector(".btn-log-trade");
    if (btn) {
      btn.textContent = "Error!";
      setTimeout(() => { btn.textContent = "Log This Trade"; }, 1500);
    }
  }
}

function switchJournalTab(tab) {
  journalActiveTab = tab;
  document.querySelectorAll('.journal-tab').forEach(t => t.classList.remove('active'));
  document.querySelectorAll('.journal-tab-content').forEach(c => c.classList.remove('active'));
  const tabBtn = document.getElementById('jtab-' + tab);
  const tabContent = document.getElementById('journal-' + tab);
  if (tabBtn) tabBtn.classList.add('active');
  if (tabContent) tabContent.classList.add('active');
}

async function fetchJournal() {
  try {
    const [openRes, closedRes, statsRes] = await Promise.all([
      fetch("/api/trades?status=open"),
      fetch("/api/trades?status=closed"),
      fetch("/api/trades/stats"),
    ]);
    const openTrades = await openRes.json();
    const closedTrades = await closedRes.json();
    const stats = await statsRes.json();

    renderOpenTrades(openTrades);
    renderClosedTrades(closedTrades);
    renderStats(stats);
  } catch (e) {}
}

function renderOpenTrades(trades) {
  const el = document.getElementById("journal-open");
  if (!el) return;

  if (!trades.length) {
    el.innerHTML = '<div class="journal-empty">No open trades.</div>';
    return;
  }

  const rows = trades.map(t => {
    const pnl = t.pnl_usdt != null ? t.pnl_usdt : 0;
    const pnlClass = pnl >= 0 ? 'pnl-green' : 'pnl-red';
    const pnlDisplay = pnl >= 0 ? '+' + pnl.toFixed(2) : pnl.toFixed(2);
    return `<tr>
      <td><strong>${t.symbol ? t.symbol.replace('/USDT','') : '—'}</strong></td>
      <td><span class="direction-badge ${t.direction}" style="padding:2px 8px;font-size:10px">${t.direction}</span></td>
      <td style="font-family:monospace">${fmtPrice(t.entry_price)}</td>
      <td style="font-family:monospace">${fmtPrice(t.stop_loss)}</td>
      <td class="${pnlClass}">—</td>
      <td><span class="leverage-badge" style="padding:2px 6px;font-size:10px">${t.leverage}x</span></td>
      <td style="color:var(--muted);font-size:11px">${t.opened_at || '—'}</td>
      <td id="close-action-${t.id}">
        <button class="btn-close-trade" onclick="showCloseForm(${t.id})">Close</button>
      </td>
    </tr>`;
  }).join('');

  el.innerHTML = `<table class="journal-table">
    <thead><tr>
      <th>Symbol</th><th>Direction</th><th>Entry</th><th>SL</th><th>Current P&L</th><th>Leverage</th><th>Opened</th><th></th>
    </tr></thead>
    <tbody>${rows}</tbody>
  </table>`;
}

function showCloseForm(tradeId) {
  const td = document.getElementById('close-action-' + tradeId);
  if (!td) return;
  td.innerHTML = `<div class="close-trade-form">
    <input type="number" class="close-trade-input" id="exit-price-${tradeId}" placeholder="Exit price" step="any">
    <button class="btn-confirm-close" onclick="closeTrade(${tradeId})">Close</button>
    <button class="btn-cancel-close" onclick="fetchJournal()">Cancel</button>
  </div>`;
  const input = document.getElementById('exit-price-' + tradeId);
  if (input) input.focus();
}

async function closeTrade(tradeId) {
  const input = document.getElementById('exit-price-' + tradeId);
  if (!input || !input.value) return;

  try {
    const res = await fetch('/api/trades/' + tradeId, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ exit_price: parseFloat(input.value) }),
    });
    if (!res.ok) throw new Error('Failed to close trade');
    fetchJournal();
  } catch (e) {}
}

function renderClosedTrades(trades) {
  const el = document.getElementById("journal-closed");
  if (!el) return;

  if (!trades.length) {
    el.innerHTML = '<div class="journal-empty">No closed trades yet.</div>';
    return;
  }

  const rows = trades.map(t => {
    const pnlUsdt = t.pnl_usdt != null ? t.pnl_usdt : 0;
    const pnlPct = t.pnl_pct != null ? t.pnl_pct : 0;
    const pnlClass = pnlUsdt >= 0 ? 'pnl-green' : 'pnl-red';
    const pnlUsdtDisplay = (pnlUsdt >= 0 ? '+$' : '-$') + Math.abs(pnlUsdt).toFixed(2);
    const pnlPctDisplay = (pnlPct >= 0 ? '+' : '') + pnlPct.toFixed(2) + '%';
    let duration = '—';
    if (t.opened_at && t.closed_at) {
      const ms = new Date(t.closed_at) - new Date(t.opened_at);
      const mins = Math.floor(ms / 60000);
      if (mins < 60) duration = mins + 'm';
      else if (mins < 1440) duration = Math.floor(mins / 60) + 'h ' + (mins % 60) + 'm';
      else duration = Math.floor(mins / 1440) + 'd ' + Math.floor((mins % 1440) / 60) + 'h';
    }
    return `<tr>
      <td><strong>${t.symbol ? t.symbol.replace('/USDT','') : '—'}</strong></td>
      <td><span class="direction-badge ${t.direction}" style="padding:2px 8px;font-size:10px">${t.direction}</span></td>
      <td style="font-family:monospace">${fmtPrice(t.entry_price)}</td>
      <td style="font-family:monospace">${fmtPrice(t.exit_price)}</td>
      <td class="${pnlClass}">${pnlUsdtDisplay}</td>
      <td class="${pnlClass}">${pnlPctDisplay}</td>
      <td><span class="leverage-badge" style="padding:2px 6px;font-size:10px">${t.leverage}x</span></td>
      <td style="color:var(--muted);font-size:11px">${duration}</td>
    </tr>`;
  }).join('');

  el.innerHTML = `<table class="journal-table">
    <thead><tr>
      <th>Symbol</th><th>Direction</th><th>Entry</th><th>Exit</th><th>P&L (USDT)</th><th>P&L (%)</th><th>Leverage</th><th>Duration</th>
    </tr></thead>
    <tbody>${rows}</tbody>
  </table>`;
}

function renderStats(stats) {
  const el = document.getElementById("journal-stats");
  if (!el) return;

  const wrColor = stats.win_rate > 50 ? 'var(--green)' : stats.win_rate < 50 ? 'var(--red)' : 'var(--text)';
  const pnlColor = stats.total_pnl_usdt > 0 ? 'var(--green)' : stats.total_pnl_usdt < 0 ? 'var(--red)' : 'var(--text)';
  const pnlSign = stats.total_pnl_usdt >= 0 ? '+$' : '-$';
  const bestSign = stats.best_trade_pnl >= 0 ? '+$' : '-$';
  const worstSign = stats.worst_trade_pnl >= 0 ? '+$' : '-$';

  el.innerHTML = `<div class="stats-grid">
    <div class="stat-card">
      <div class="stat-card-label">Total Trades</div>
      <div class="stat-card-value">${stats.total_trades}</div>
    </div>
    <div class="stat-card">
      <div class="stat-card-label">Win Rate</div>
      <div class="stat-card-value" style="color:${wrColor}">${stats.win_rate.toFixed(1)}%</div>
    </div>
    <div class="stat-card">
      <div class="stat-card-label">Total P&L</div>
      <div class="stat-card-value" style="color:${pnlColor}">${pnlSign}${Math.abs(stats.total_pnl_usdt).toFixed(2)}</div>
    </div>
    <div class="stat-card">
      <div class="stat-card-label">Avg Return</div>
      <div class="stat-card-value">${stats.avg_rr >= 0 ? '+' : ''}${stats.avg_rr.toFixed(2)}%</div>
    </div>
    <div class="stat-card">
      <div class="stat-card-label">Best Trade</div>
      <div class="stat-card-value" style="color:var(--green)">${bestSign}${Math.abs(stats.best_trade_pnl).toFixed(2)}</div>
    </div>
    <div class="stat-card">
      <div class="stat-card-label">Worst Trade</div>
      <div class="stat-card-value" style="color:var(--red)">${worstSign}${Math.abs(stats.worst_trade_pnl).toFixed(2)}</div>
    </div>
    <div class="stat-card">
      <div class="stat-card-label">Win Streak</div>
      <div class="stat-card-value" style="color:var(--green)">${stats.win_streak}</div>
    </div>
    <div class="stat-card">
      <div class="stat-card-label">Loss Streak</div>
      <div class="stat-card-value" style="color:var(--red)">${stats.loss_streak}</div>
    </div>
  </div>`;
}

// ── Settings ───────────────────────────────────────────────────────────────
window._settingsCache = null;
let settingsDebounceTimer = null;

async function loadSettings() {
  try {
    const res = await fetch("/api/settings");
    const data = await res.json();
    window._settingsCache = data;
    const balEl = document.getElementById("setting-balance");
    const riskEl = document.getElementById("setting-risk");
    const levEl = document.getElementById("setting-leverage");
    if (balEl) balEl.value = data.account_balance;
    if (riskEl) riskEl.value = (data.risk_pct * 100).toFixed(1);
    if (levEl) levEl.value = data.max_leverage;
  } catch (e) {}
}

function attachSettingsListeners() {
  // Populate values from cached settings
  if (window._settingsCache) {
    const s = window._settingsCache;
    const balEl = document.getElementById("setting-balance");
    const riskEl = document.getElementById("setting-risk");
    const levEl = document.getElementById("setting-leverage");
    if (balEl) balEl.value = s.account_balance;
    if (riskEl) riskEl.value = (s.risk_pct * 100).toFixed(1);
    if (levEl) levEl.value = s.max_leverage;
  }
  const ids = ["setting-balance", "setting-risk", "setting-leverage"];
  ids.forEach(id => {
    const el = document.getElementById(id);
    if (el) {
      el.removeEventListener("input", onSettingChange);
      el.addEventListener("input", onSettingChange);
    }
  });
}

function onSettingChange() {
  clearTimeout(settingsDebounceTimer);
  settingsDebounceTimer = setTimeout(saveSettingsFromUI, 500);
}

async function saveSettingsFromUI() {
  const balEl = document.getElementById("setting-balance");
  const riskEl = document.getElementById("setting-risk");
  const levEl = document.getElementById("setting-leverage");
  if (!balEl || !riskEl || !levEl) return;

  const payload = {
    account_balance: parseFloat(balEl.value) || 1000,
    risk_pct: (parseFloat(riskEl.value) || 2) / 100,
    max_leverage: parseInt(levEl.value) || 5,
  };

  try {
    const res = await fetch("/api/settings", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    window._settingsCache = await res.json();
    const indicator = document.getElementById("settings-saved-indicator");
    if (indicator) {
      indicator.classList.add("show");
      setTimeout(() => indicator.classList.remove("show"), 1500);
    }
    // Re-fetch trade setup with new settings
    const currentData = allData[activeSymbol];
    if (currentData) fetchTradeSetup(activeSymbol, currentData.signal);
  } catch (e) {}
}

// ── Trading Guide Toggle ───────────────────────────────────────────────────
function toggleGuide() {
  const content = document.getElementById("guide-content");
  const arrow = document.getElementById("guide-arrow");
  if (!content) return;
  content.classList.toggle("open");
  if (arrow) arrow.classList.toggle("open");
}

// ── Countdown timer ────────────────────────────────────────────────────────
function resetCountdown() {
  countdownVal = getRefreshInterval();
  clearInterval(countdownTimer);
  const el = document.getElementById("countdown");
  if (el) el.textContent = countdownVal;
  countdownTimer = setInterval(() => {
    countdownVal--;
    const el = document.getElementById("countdown");
    if (el) el.textContent = countdownVal;
    if (countdownVal <= 0) {
      loadSymbol(activeSymbol, true);
    }
  }, 1000);
}

// ── Fetch history ──────────────────────────────────────────────────────────
async function fetchHistory() {
  try {
    const res = await fetch("/api/history");
    window._history = await res.json();
  } catch (e) {}
}

// ── Init ───────────────────────────────────────────────────────────────────
(async () => {
  renderTabs();
  await Promise.all([fetchHistory(), loadSettings()]);
  await loadSymbol(activeSymbol);
  await loadAllSymbols();  // load rest for tab badges
  resetCountdown();
})();
</script>
</body>
</html>
"""


# ─── Routes ────────────────────────────────────────────────────────────────────
@app.route("/")
def index():
    return render_template_string(DASHBOARD_HTML, symbols=SYMBOLS)


@app.route("/api/analyze")
def api_analyze():
    symbol = request.args.get("symbol", SYMBOLS[0])
    if symbol not in SYMBOLS:
        return jsonify({"error": "Unknown symbol"}), 400
    force = request.args.get("force", "0") == "1"
    if force:
        with cache_lock:
            cache.pop(symbol, None)
    data = get_cached_analysis(symbol)
    return jsonify(data)


@app.route("/api/history")
def api_history():
    return jsonify(signal_history)


@app.route("/api/symbols")
def api_symbols():
    return jsonify(SYMBOLS)


@app.route("/api/trade-setup")
def api_trade_setup():
    symbol = request.args.get("symbol", SYMBOLS[0])
    if symbol not in SYMBOLS:
        return jsonify({"error": "Unknown symbol"}), 400
    settings = load_settings()
    balance = float(request.args.get("balance", settings["account_balance"]))
    risk_pct = float(request.args.get("risk_pct", settings["risk_pct"]))
    max_lev = int(request.args.get("max_leverage", settings["max_leverage"]))
    analysis = get_cached_analysis(symbol)
    setup = calculate_trade_setup(analysis, balance, risk_pct, max_lev)
    if setup is None:
        return jsonify({"error": "No active signal", "signal": analysis["signal"]}), 200
    return jsonify(setup)


@app.route("/api/settings", methods=["GET"])
def api_get_settings():
    return jsonify(load_settings())


@app.route("/api/settings", methods=["POST"])
def api_save_settings():
    data = request.get_json(force=True)
    settings = load_settings()
    if "account_balance" in data:
        settings["account_balance"] = float(data["account_balance"])
    if "risk_pct" in data:
        settings["risk_pct"] = float(data["risk_pct"])
    if "max_leverage" in data:
        settings["max_leverage"] = int(data["max_leverage"])
    save_settings(settings)
    return jsonify(settings)


# ─── Trade Journal API ─────────────────────────────────────────────────────────
@app.route("/api/trades", methods=["GET"])
def api_get_trades():
    status = request.args.get("status", "all")
    trades = load_trades()
    if status == "open":
        trades = [t for t in trades if t.get("status") == "open"]
    elif status == "closed":
        trades = [t for t in trades if t.get("status") == "closed"]
    return jsonify(trades)


@app.route("/api/trades", methods=["POST"])
def api_create_trade():
    data = request.get_json(force=True)
    with trades_lock:
        trades = load_trades()
        trade = {
            "id": int(time.time() * 1000),
            "symbol": data.get("symbol", ""),
            "direction": data.get("direction", ""),
            "entry_price": float(data.get("entry_price", 0)),
            "stop_loss": float(data.get("stop_loss", 0)),
            "tp1": float(data.get("tp1", 0)),
            "tp2": float(data.get("tp2", 0)),
            "tp3": float(data.get("tp3", 0)),
            "leverage": int(data.get("leverage", 2)),
            "position_size_usdt": float(data.get("position_size_usdt", 0)),
            "position_size_coin": float(data.get("position_size_coin", 0)),
            "risk_pct": float(data.get("risk_pct", 0.02)),
            "risk_amount": float(data.get("risk_amount", 0)),
            "confidence_score": float(data.get("confidence_score", 0)),
            "status": "open",
            "exit_price": None,
            "exit_reason": None,
            "pnl_usdt": None,
            "pnl_pct": None,
            "opened_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S UTC"),
            "closed_at": None,
            "notes": data.get("notes", ""),
        }
        trades.insert(0, trade)
        save_trades(trades)
    return jsonify(trade), 201


@app.route("/api/trades/<int:trade_id>", methods=["PUT"])
def api_update_trade(trade_id):
    data = request.get_json(force=True)
    with trades_lock:
        trades = load_trades()
        trade = next((t for t in trades if t["id"] == trade_id), None)
        if trade is None:
            return jsonify({"error": "Trade not found"}), 404

        if "exit_price" in data and data["exit_price"] is not None:
            exit_price = float(data["exit_price"])
            trade["exit_price"] = exit_price
            trade["exit_reason"] = data.get("exit_reason", "manual")
            trade["status"] = "closed"
            trade["closed_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S UTC")

            entry = trade["entry_price"]
            if trade["direction"] == "LONG":
                trade["pnl_pct"] = round((exit_price - entry) / entry * 100, 2)
            else:
                trade["pnl_pct"] = round((entry - exit_price) / entry * 100, 2)
            trade["pnl_usdt"] = round(
                trade["position_size_usdt"] * (trade["pnl_pct"] / 100), 2
            )

        if "notes" in data:
            trade["notes"] = data["notes"]

        save_trades(trades)
    return jsonify(trade)


@app.route("/api/trades/stats")
def api_trade_stats():
    trades = load_trades()
    closed = [t for t in trades if t.get("status") == "closed"]

    if not closed:
        return jsonify({
            "total_trades": len(trades),
            "open_trades": len([t for t in trades if t.get("status") == "open"]),
            "closed_trades": 0,
            "win_rate": 0,
            "avg_rr": 0,
            "total_pnl_usdt": 0,
            "total_pnl_pct": 0,
            "best_trade_pnl": 0,
            "worst_trade_pnl": 0,
            "win_streak": 0,
            "loss_streak": 0,
        })

    wins = [t for t in closed if (t.get("pnl_usdt") or 0) > 0]
    losses = [t for t in closed if (t.get("pnl_usdt") or 0) <= 0]
    pnls = [t.get("pnl_usdt", 0) or 0 for t in closed]
    pnl_pcts = [t.get("pnl_pct", 0) or 0 for t in closed]

    # Calculate streaks
    win_streak = 0
    loss_streak = 0
    current_streak = 0
    last_was_win = None
    for t in reversed(closed):
        is_win = (t.get("pnl_usdt") or 0) > 0
        if last_was_win is None or is_win == last_was_win:
            current_streak += 1
        else:
            current_streak = 1
        last_was_win = is_win
        if is_win:
            win_streak = max(win_streak, current_streak)
        else:
            loss_streak = max(loss_streak, current_streak)

    return jsonify({
        "total_trades": len(trades),
        "open_trades": len([t for t in trades if t.get("status") == "open"]),
        "closed_trades": len(closed),
        "win_rate": round(len(wins) / len(closed) * 100, 1) if closed else 0,
        "avg_rr": round(sum(pnl_pcts) / len(pnl_pcts), 2) if pnl_pcts else 0,
        "total_pnl_usdt": round(sum(pnls), 2),
        "total_pnl_pct": round(sum(pnl_pcts), 2),
        "best_trade_pnl": round(max(pnls), 2) if pnls else 0,
        "worst_trade_pnl": round(min(pnls), 2) if pnls else 0,
        "win_streak": win_streak,
        "loss_streak": loss_streak,
    })


# ─── Entry Point ───────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("\n" + "="*55)
    print("  Crypto Signal Dashboard")
    print("  Connecting to ByBit (free, no API key needed)")
    print("  Open: http://localhost:5001")
    print("="*55 + "\n")
    app.run(debug=False, host="0.0.0.0", port=5001)
