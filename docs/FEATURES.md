# Feature Specifications

Feature specs live in `docs/sk:features/`. Each spec is the single source of truth for one feature — covering business logic, API contract, edge cases, and UI behavior.

## How to Use

- **Reading a spec**: open `docs/sk:features/<feature>.md`
- **Updating a spec**: run `/sk:features` after shipping changes
- **Adding a new spec**: copy `docs/sk:features/_template.md`, fill all 11 sections, add a row to this index

## Feature Index

| Feature | Spec | Status | Description |
|---------|------|--------|-------------|
| Signal Engine | [signal-engine.md](sk:features/signal-engine.md) | ✅ Web | 6-rule confluence signal detection with confidence scoring and funding rate block |
| Trade Journal | [trade-journal.md](sk:features/trade-journal.md) | ✅ Web | Trade tracking, PnL calculation, and aggregate statistics |
| Trade Setup Calculator | [trade-setup.md](sk:features/trade-setup.md) | ✅ Web | ATR-based SL/TP levels and risk-based position sizing |

## Architecture Overview

Single-file Python/Flask app (`app.py`) serving a dashboard at `http://localhost:5001`.

```
analyzer.py      — signal engine, rule functions, trade setup calculator
app.py           — Flask server + embedded dashboard HTML/CSS/JS
data/
  signals.json   — signal history (persisted)
  trades.json    — trade journal (persisted)
  settings.json  — user settings (persisted)
tests/
  test_analyzer.py — 62 pytest tests
```

**Exchange:** ByBit via ccxt (public endpoints only — no API key required)
**Cache:** In-memory per-symbol, 60s TTL, thread-safe
**Persistence:** Flat JSON files in `data/` — no database

## No Tiers / Subscriptions

This is a personal local tool. No user accounts, no tiers, no auth.
