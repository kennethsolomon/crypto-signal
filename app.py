"""
app.py - Crypto Trading Signal Dashboard
Run: python app.py
Then open: http://localhost:5000
"""

from flask import Flask, jsonify, render_template_string, request
from flask.json.provider import DefaultJSONProvider
from analyzer import analyze, SYMBOLS
from datetime import datetime
import threading
import time
import numpy as np


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

# ─── Signal History (in-memory, last 50 signals) ──────────────────────────────
signal_history = []
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
            })
            # Keep only last 50 signals
            del signal_history[50:]

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

    .fill-green { background: var(--green); }
    .fill-red   { background: var(--red); }
    .fill-gray  { background: var(--muted); }

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
    <span>Live via Binance</span>
    <span>|</span>
    <span>Refresh in <strong id="countdown">60</strong>s</span>
    <button onclick="loadSymbol(activeSymbol, true)" style="
      background: var(--accent); border: none; color: #fff;
      padding: 6px 14px; border-radius: 6px; cursor: pointer; font-size: 12px;">
      ↻ Refresh Now
    </button>
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

  const fillClass = data.signal === "BUY" ? "fill-green" : data.signal === "SELL" ? "fill-red" : "fill-gray";
  const pct = data.signal === "BUY" ? longPct : data.signal === "SELL" ? shortPct : Math.max(longPct, shortPct);

  const priceDisplay = data.current_price
    ? `$${Number(data.current_price).toLocaleString("en-US", {minimumFractionDigits: 2, maximumFractionDigits: 6})}`
    : "—";

  // Rules HTML
  const rulesHtml = data.rules.map(r => {
    const icon = r.long && r.short ? "✅" : r.long ? "🟢" : r.short ? "🔴" : "⬜";
    const longPill = `<span class="pill ${r.long ? 'pill-pass-long' : 'pill-fail-long'}">${r.long ? "✓ LONG" : "✗ LONG"}</span>`;
    const shortPill = `<span class="pill ${r.short ? 'pill-pass-short' : 'pill-fail-short'}">${r.short ? "✓ SHORT" : "✗ SHORT"}</span>`;
    return `
      <div class="rule-row">
        <div class="rule-icon">${icon}</div>
        <div style="flex:1">
          <div class="rule-name">${r.rule}</div>
          <div class="rule-desc">${r.description || ""}</div>
          <div class="rule-value">${r.value || ""}</div>
          <div class="rule-pills">${longPill}${shortPill}</div>
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

  document.getElementById("content").innerHTML = `
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
          <div class="progress-label">Confluence Score (${pct}%)</div>
          <div class="progress-bar-wrap">
            <div class="progress-bar-fill ${fillClass}" style="width:${pct}%"></div>
          </div>
        </div>

        <!-- Rules Panel -->
        <div class="rules-panel">
          <div class="rules-header">📋 Rule Checklist — All 5 must pass</div>
          ${rulesHtml}
        </div>
      </div>

      <!-- Right Column -->
      <div class="right-col">

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
            <div class="fw-value">Binance (Free API)</div>
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

      </div>
    </div>`;
}

// ── Countdown timer ────────────────────────────────────────────────────────
function resetCountdown() {
  countdownVal = 60;
  clearInterval(countdownTimer);
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
  await fetchHistory();
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


# ─── Entry Point ───────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("\n" + "="*55)
    print("  🚀  Crypto Signal Dashboard")
    print("  📡  Connecting to Binance (free, no API key needed)")
    print("  🌐  Open: http://localhost:5001")
    print("="*55 + "\n")
    app.run(debug=False, host="0.0.0.0", port=5001)
