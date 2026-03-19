# Crypto Signal Dashboard

A real-time cryptocurrency trading signal analyzer using a 5-rule confluence framework. Analyzes multiple trading pairs on Binance and displays high-quality buy/sell signals based on technical indicators.

## Quick Start

### Prerequisites

- Python 3.10 or newer
- Internet connection (fetches data from Binance public API)
- No API key required

### Installation

1. **Clone and navigate to the project:**
   ```bash
   cd crypto-signal
   ```

2. **Create a virtual environment (optional but recommended):**
   ```bash
   python3 -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

### Running the App

```bash
python app.py
```

The dashboard will start at: **http://localhost:5000**

## Dependencies

| Package | Version | Purpose |
|---------|---------|---------|
| Flask | >=3.0.0 | Web framework for dashboard |
| CCXT | >=4.3.0 | Cryptocurrency exchange data |
| Pandas | >=2.2.0 | Data manipulation & analysis |
| Pandas-TA | >=0.3.14b | Technical analysis indicators |

## Features

### Confidence-Scored Signals
Signals are scored using a weighted 5-rule confluence system. Each rule contributes to an overall confidence percentage, so you can prioritize the strongest setups.

### Signal Forming Alerts
Get early heads-up notifications when 3-4 out of 5 rules are passing. These "forming" alerts let you prepare before a full signal fires.

### Trade Setup Card
Every signal includes a complete trade setup: entry price, stop loss, three take-profit targets (TP1-3), suggested leverage, and calculated position size based on your account settings.

### One-Click Copy to Clipboard
Copy trade parameters in ByBit-ready format with a single click for fast order entry.

### Account Settings
Configure your account balance, risk percentage per trade, and maximum leverage. These settings drive the position sizing calculations in every trade setup.

### Real-Time / Polling Toggle
Switch between real-time mode (10-second refresh) and polling mode (60-second refresh) depending on your needs and connection.

### Trade Journal
Log trades, mark them as closed, and track profit/loss for each position. All journal entries persist locally.

### Performance Stats
View aggregated statistics including win rate, average risk-to-reward ratio, and win/loss streaks calculated from your trade journal.

### Browser Notifications & Audio Alerts
Receive browser push notifications and audio alerts when new signals fire, so you never miss a setup.

### Built-In Trading Guide
An integrated guide with step-by-step ByBit instructions for placing trades based on the dashboard signals.

## How It Works

### The 5-Rule Confluence Framework

A signal fires **ONLY when ALL 5 rules pass simultaneously**, ensuring high-quality entries and limiting you to 1-2 trades per day.

#### Rule 1 — Trend Alignment (4H timeframe)
- **Long**: Price above 200 EMA (bullish)
- **Short**: Price below 200 EMA (bearish)

#### Rule 2 — RSI Momentum (1H timeframe)
- **Long**: RSI between 50-70 AND rising
- **Short**: RSI between 30-50 AND falling

#### Rule 3 — MACD Crossover (1H timeframe)
- **Long**: MACD crossed above signal line in last 3 candles
- **Short**: MACD crossed below signal line in last 3 candles

#### Rule 4 — EMA Stack (15M timeframe)
- **Long**: Price > EMA9 > EMA21
- **Short**: Price < EMA9 < EMA21

#### Rule 5 — Volume Surge (15M timeframe)
- Current volume must be >= 1.2x the 20-candle average

## Supported Trading Pairs

Default pairs: **BTC/USDT, ETH/USDT, SOL/USDT, BNB/USDT, XRP/USDT, DOGE/USDT**

To add more pairs, edit the `SYMBOLS` list in `analyzer.py`.

## Data Persistence

The `data/` directory stores all user-specific state locally:

| File | Purpose |
|------|---------|
| `trades.json` | Trade journal entries (open and closed positions) |
| `signals.json` | Cached signal history |
| `settings.json` | Account settings (balance, risk %, max leverage) |

This directory is git-ignored. Each user maintains their own local data.

## Disclaimer

**This tool is for informational purposes only.**

- Trading cryptocurrencies involves significant risk of loss
- Always use proper risk management and position sizing
- Never trade more than you can afford to lose
- Past performance does not guarantee future results
- Always do your own research (DYOR) before trading

## License

This project is provided as-is for educational purposes.
