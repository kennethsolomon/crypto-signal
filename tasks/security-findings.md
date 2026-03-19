# Security Findings

> Populated by `/security-check`. Never overwritten — new audits append below.
> Referenced by `/review`, `/finish-feature`, and `/brainstorm` for security context.


---

# Security Audit — 2026-03-19

**Scope:** Changed files on branch `feature/signal-rule-upgrade-state-based`
**Stack:** Python / Flask / ccxt
**Files audited:** 7 (`analyzer.py`, `app.py`, `requirements.txt`, `tests/test_analyzer.py`, `tasks/findings.md`, `tasks/todo.md`, `tasks/workflow-status.md`)

---

## Critical

*None.*

---

## High

*None.*

---

## Medium

- [x] **[app.py:2595–2605, 2630]** Unhandled `ValueError`/`TypeError` in trade API endpoints *(resolved — try/except added in api_create_trade and api_update_trade)*
  **Standard:** OWASP A05 — Security Misconfiguration (CWE-703, CWE-209)
  **Risk:** `float(data.get("entry_price", 0))` and similar casts on 9 POST/PUT fields raise an unhandled exception when the client sends non-numeric values (e.g. `"entry_price": "abc"`). Flask returns HTTP 500 with a Python traceback in development mode, or a generic 500 in production. Tracebacks can reveal internal file paths and code structure.
  **Recommendation:** Wrap the entire `api_create_trade` and `api_update_trade` bodies in a `try/except (ValueError, TypeError, KeyError)` block and return `jsonify({"error": "Invalid trade data"}), 400`.

- [x] **[app.py:2531]** `timeframe` query parameter passed to ccxt without allowlist validation *(resolved — ALLOWED_TIMEFRAMES set added, returns 400 on unknown value)*
  **Standard:** OWASP A04 — Insecure Design (CWE-20)
  **Risk:** Any string is forwarded to `get_chart_data()` and then to `exchange.fetch_ohlcv()`. While ccxt handles invalid timeframes gracefully, an arbitrary string could trigger unexpected ccxt error paths or cause inconsistent server-side behaviour.
  **Recommendation:** Validate against an explicit allowlist: `ALLOWED_TIMEFRAMES = {"1m","5m","15m","1h","4h","1d"}`. Return 400 if not in the set.

- [x] **[app.py:2532]** `limit` query parameter converted with `int()` without exception handling *(resolved — uses Flask's type=int which returns default on failure)*
  **Standard:** OWASP A05 — Security Misconfiguration (CWE-703)
  **Risk:** `int(request.args.get("limit", 100))` raises an unhandled `ValueError` if the client sends a non-integer string (e.g. `?limit=abc`), resulting in an HTTP 500.
  **Recommendation:** Use `int(request.args.get("limit", 100) or 100)` inside a try/except, or use Flask's `request.args.get("limit", 100, type=int)` which safely returns the default on parse failure.

- [x] **[app.py:2545–2547, 2564–2569]** No bounds validation on financial parameters *(resolved — balance≥1, risk_pct 0.1%–10%, leverage 1–20 clamped in api_trade_setup and api_save_settings)*
  **Standard:** OWASP A04 — Insecure Design (CWE-20)
  **Risk:** `balance`, `risk_pct`, and `max_leverage` accept any numeric value from query params and stored settings — e.g. `balance=-1`, `risk_pct=500`, `max_leverage=1000`. These propagate into `calculate_trade_setup()`, producing nonsensical position sizes. A compromised or buggy client could corrupt the stored settings file.
  **Recommendation:** Clamp values to sane ranges after parsing: `balance > 0`, `0 < risk_pct <= 0.10` (10% max), `1 <= max_leverage <= 20`.

---

## Low / Informational

- [x] **[app.py:2719]** Server binds to `host="0.0.0.0"` with no authentication *(resolved — changed to host="127.0.0.1")*
  **Standard:** OWASP A01 — Broken Access Control (CWE-306) — informational for a personal local tool
  **Risk:** Any device on the same network (local Wi-Fi, VPN) can read the trade journal, signal history, and settings, and can create/close trades without any credential. Acceptable for a strictly localhost workflow; becomes a risk on shared or public networks.
  **Recommendation:** For personal use, change to `host="127.0.0.1"`. If network access is needed, add HTTP Basic Auth via Flask-HTTPAuth or a simple API-key header check.

- [x] **[analyzer.py:60]** Full exception message printed to stdout in `fetch_funding_rate` *(accepted — local tool, no log forwarding)*
  **Standard:** OWASP A09 — Logging Failures (CWE-209)
  **Risk:** Exception messages from ccxt may include exchange-specific error payloads. For a local tool this is acceptable, but worth noting in case logs are forwarded.
  **Recommendation:** Acceptable as-is for a local tool. If logs are ever shipped, redact exchange error bodies.

---

## Passed Checks

- **Injection (SQL, OS command, template)** — No SQL, no `subprocess`, no `eval`/`exec`, no template injection. `render_template_string` renders a static string literal with no user-controlled variables merged in.
- **XSS** — All user-generated fields in the journal (`symbol`, `direction`, numeric fields) are controlled server-side. The frontend uses `.textContent` for server data in almost all cases. Symbol data always comes from the validated `SYMBOLS` allowlist; no free-form strings are inserted via `innerHTML`.
- **Hardcoded secrets** — No API keys, tokens, or passwords in source. The ccxt ByBit exchange is used in anonymous read-only mode (public endpoints only).
- **Debug mode** — `app.run(debug=False)` confirmed at line 2719. Debug mode is off.
- **Symbol allowlist** — All four API endpoints that accept `symbol` validate it against `SYMBOLS` before use (`api/analyze`, `api/chart-data`, `api/trade-setup` return 400 for unknown symbols). No injection vector via symbol.
- **Cryptographic failures** — No cryptographic operations in scope. No passwords stored.
- **Dependency audit** — `pip-audit` run clean (confirmed in Step 12 lint gate).
- **Funding rate logic** — New `fetch_funding_rate` uses the ccxt public endpoint; symbol conversion (`/USDT` → `/USDT:USDT`) is applied to a server-controlled value, not user input.
- **StochRSI / OBV / MACD** — New rule functions operate on exchange-fetched OHLCV data, not user input. Error paths return safe defaults.

---

## Summary

| Severity | Open | Resolved this run |
|----------|------|-------------------|
| Critical | 0    | 0                 |
| High     | 0    | 0                 |
| Medium   | 0    | 4                 |
| Low      | 0    | 2                 |
| **Total** | **0** | **6**            |
