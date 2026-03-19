"""
TDD tests for signal rule upgrade (Option B).

Covers:
  - Rule 3: MACD Histogram State (replaces MACD Crossover event)
  - Rule 5: OBV Trend (replaces Volume Surge event)
  - Rule 6: Stochastic RSI entry timing (new function)
  - fetch_funding_rate: ByBit funding rate fetcher (new function)
  - analyze(): 6-rule system, 5/6 threshold, funding rate override
"""

import pytest
import pandas as pd
from contextlib import ExitStack
from datetime import datetime, timedelta
from unittest.mock import patch

import analyzer


# ─── Test Helpers ─────────────────────────────────────────────────────────────


def make_ohlcv(n: int, close_prices=None, volume=None) -> pd.DataFrame:
    base_time = datetime(2026, 3, 19, 12, 0, 0)
    closes = (
        close_prices
        if close_prices is not None
        else [100.0 + i * 0.1 for i in range(n)]
    )
    vols = volume if volume is not None else [1000.0] * n
    return pd.DataFrame(
        {
            "timestamp": [base_time + timedelta(hours=i) for i in range(n)],
            "open": [c - 0.5 for c in closes],
            "high": [c + 1.0 for c in closes],
            "low": [c - 1.0 for c in closes],
            "close": closes,
            "volume": vols,
        }
    )


def make_rule(long: bool, short: bool, strength: float = 0.5) -> dict:
    return {
        "rule": "Test Rule",
        "description": "test",
        "long": long,
        "short": short,
        "strength": strength,
        "value": "test",
        "signal_hint": "test",
        "error": False,
    }


NEUTRAL_FUNDING = {"rate": 0.0001, "extreme": False, "blocked_side": None}
BLOCK_LONG = {"rate": 0.0006, "extreme": True, "blocked_side": "LONG"}
BLOCK_SHORT = {"rate": -0.0006, "extreme": True, "blocked_side": "SHORT"}


def patch_analyze(long_flags, short_flags, funding=None, price_df=None, strength=0.5):
    """Return a list of patches that control all 6 rules + funding + price."""
    if funding is None:
        funding = NEUTRAL_FUNDING
    if price_df is None:
        price_df = make_ohlcv(2, close_prices=[50000.0, 50100.0])

    rule_fns = [
        "check_rule_1_trend",
        "check_rule_2_rsi",
        "check_rule_3_macd",
        "check_rule_4_ema_stack",
        "check_rule_5_volume",
        "check_rule_6_stoch_rsi",
    ]
    patches = [
        patch(f"analyzer.{fn}", return_value=make_rule(long_flags[i], short_flags[i], strength))
        for i, fn in enumerate(rule_fns)
    ]
    patches.append(patch("analyzer.fetch_funding_rate", return_value=funding))
    patches.append(patch("analyzer.fetch_ohlcv", return_value=price_df))
    return patches


# ─── Rule 3: MACD Histogram State ─────────────────────────────────────────────


class TestRule3MacdHistogram:
    def _call_with_histogram(self, hist_vals):
        df = make_ohlcv(100)
        macd_df = pd.DataFrame(
            {
                "MACD_12_26_9": [0.1] * 100,
                "MACDs_12_26_9": [0.0] * 100,
                "MACDh_12_26_9": hist_vals,
            }
        )
        with patch("analyzer.fetch_ohlcv", return_value=df):
            with patch("analyzer.ta") as mock_ta:
                mock_ta.macd.return_value = macd_df
                return analyzer.check_rule_3_macd("BTC/USDT")

    def test_rule_name_reflects_histogram_logic(self):
        result = self._call_with_histogram([0.1, 0.2, 0.3] * 33 + [0.1])
        assert "Histogram" in result["rule"] or "histogram" in result["rule"].lower()

    def test_long_when_histogram_positive_and_growing(self):
        # last 3: 0.1, 0.2, 0.3 — positive and growing
        hist = [0.0] * 97 + [0.1, 0.2, 0.3]
        result = self._call_with_histogram(hist)
        assert result["long"] is True
        assert result["short"] is False
        assert result["error"] is False

    def test_short_when_histogram_negative_and_falling(self):
        # last 3: -0.1, -0.2, -0.3 — negative and getting more negative
        hist = [0.0] * 97 + [-0.1, -0.2, -0.3]
        result = self._call_with_histogram(hist)
        assert result["long"] is False
        assert result["short"] is True

    def test_no_signal_when_histogram_positive_but_shrinking(self):
        # last 3: 0.3, 0.2, 0.1 — positive but shrinking
        hist = [0.0] * 97 + [0.3, 0.2, 0.1]
        result = self._call_with_histogram(hist)
        assert result["long"] is False
        assert result["short"] is False

    def test_no_signal_when_histogram_negative_but_shrinking(self):
        # last 3: -0.3, -0.2, -0.1 — negative but recovering (less negative)
        hist = [0.0] * 97 + [-0.3, -0.2, -0.1]
        result = self._call_with_histogram(hist)
        assert result["long"] is False
        assert result["short"] is False

    def test_no_signal_when_histogram_crosses_zero(self):
        hist = [0.0] * 97 + [-0.1, 0.0, 0.1]
        result = self._call_with_histogram(hist)
        # Not all 3 candles positive → long should not pass
        assert result["long"] is False

    def test_strength_positive_when_long_passes(self):
        hist = [0.0] * 97 + [0.1, 0.2, 0.5]
        result = self._call_with_histogram(hist)
        assert result["long"] is True
        assert 0.0 < result["strength"] <= 1.0

    def test_strength_zero_when_no_signal(self):
        hist = [0.0] * 97 + [0.3, 0.2, 0.1]
        result = self._call_with_histogram(hist)
        assert result["strength"] == 0.0

    def test_error_on_data_unavailable(self):
        with patch("analyzer.fetch_ohlcv", return_value=None):
            result = analyzer.check_rule_3_macd("BTC/USDT")
        assert result["error"] is True
        assert result["long"] is False
        assert result["short"] is False

    def test_returns_all_required_fields(self):
        with patch("analyzer.fetch_ohlcv", return_value=None):
            result = analyzer.check_rule_3_macd("BTC/USDT")
        for f in (
            "rule",
            "description",
            "long",
            "short",
            "strength",
            "value",
            "signal_hint",
            "error",
        ):
            assert f in result


# ─── Rule 5: OBV Trend ────────────────────────────────────────────────────────


class TestRule5OBVTrend:
    def test_rule_name_reflects_obv_logic(self):
        closes = [100.0 + i * 0.5 for i in range(60)]
        with patch(
            "analyzer.fetch_ohlcv", return_value=make_ohlcv(60, close_prices=closes)
        ):
            result = analyzer.check_rule_5_volume("BTC/USDT")
        assert "OBV" in result["rule"] or "obv" in result["rule"].lower()

    def test_long_when_obv_trending_up(self):
        # Consistently rising closes → every candle adds volume to OBV
        closes = [100.0 + i * 0.5 for i in range(60)]
        with patch(
            "analyzer.fetch_ohlcv",
            return_value=make_ohlcv(60, close_prices=closes, volume=[500.0] * 60),
        ):
            result = analyzer.check_rule_5_volume("BTC/USDT")
        assert result["long"] is True
        assert result["short"] is False
        assert result["error"] is False

    def test_short_when_obv_trending_down(self):
        # Consistently falling closes → every candle subtracts volume from OBV
        closes = [100.0 - i * 0.5 for i in range(60)]
        with patch(
            "analyzer.fetch_ohlcv",
            return_value=make_ohlcv(60, close_prices=closes, volume=[500.0] * 60),
        ):
            result = analyzer.check_rule_5_volume("BTC/USDT")
        assert result["long"] is False
        assert result["short"] is True

    def test_strength_in_range_when_long_passes(self):
        closes = [100.0 + i for i in range(60)]
        with patch(
            "analyzer.fetch_ohlcv",
            return_value=make_ohlcv(60, close_prices=closes, volume=[1000.0] * 60),
        ):
            result = analyzer.check_rule_5_volume("BTC/USDT")
        if result["long"]:
            assert 0.0 < result["strength"] <= 1.0

    def test_error_on_data_unavailable(self):
        with patch("analyzer.fetch_ohlcv", return_value=None):
            result = analyzer.check_rule_5_volume("BTC/USDT")
        assert result["error"] is True
        assert result["long"] is False
        assert result["short"] is False

    def test_returns_all_required_fields(self):
        with patch("analyzer.fetch_ohlcv", return_value=None):
            result = analyzer.check_rule_5_volume("BTC/USDT")
        for f in (
            "rule",
            "description",
            "long",
            "short",
            "strength",
            "value",
            "signal_hint",
            "error",
        ):
            assert f in result

    def test_no_signal_when_closes_flat_obv_zero_slope(self):
        # All closes equal → every OBV step hits the flat branch → slope = 0 → no signal
        closes = [100.0] * 60
        with patch(
            "analyzer.fetch_ohlcv",
            return_value=make_ohlcv(60, close_prices=closes),
        ):
            result = analyzer.check_rule_5_volume("BTC/USDT")
        assert result["long"] is False
        assert result["short"] is False


# ─── Rule 6: Stochastic RSI ───────────────────────────────────────────────────


class TestRule6StochRSI:
    def _call_with_stoch(self, k_vals, d_vals):
        with patch("analyzer.fetch_ohlcv", return_value=make_ohlcv(60)):
            with patch("analyzer.ta") as mock_ta:
                mock_ta.stochrsi.return_value = pd.DataFrame(
                    {
                        "STOCHRSIk_14_14_3_3": k_vals,
                        "STOCHRSId_14_14_3_3": d_vals,
                    }
                )
                return analyzer.check_rule_6_stoch_rsi("BTC/USDT")

    def test_function_exists(self):
        assert hasattr(analyzer, "check_rule_6_stoch_rsi"), (
            "check_rule_6_stoch_rsi not found — add it to analyzer.py"
        )

    def test_long_when_k_below_50_and_crosses_up(self):
        # K was below D (28 < 30), now K is above D (32 > 30) — crossover up
        k = [30.0] * 58 + [28.0, 32.0]
        d = [30.0] * 58 + [30.0, 30.0]
        result = self._call_with_stoch(k, d)
        assert result["long"] is True
        assert result["short"] is False
        assert result["error"] is False

    def test_short_when_k_above_50_and_crosses_down(self):
        # K was above D (72 > 70), now K is below D (68 < 70) — crossover down
        k = [70.0] * 58 + [72.0, 68.0]
        d = [70.0] * 58 + [70.0, 70.0]
        result = self._call_with_stoch(k, d)
        assert result["long"] is False
        assert result["short"] is True

    def test_no_long_when_k_below_50_no_crossover(self):
        # K always above D — no crossover
        k = [35.0] * 60
        d = [30.0] * 60
        result = self._call_with_stoch(k, d)
        assert result["long"] is False

    def test_no_short_when_k_above_50_no_crossover(self):
        # K always below D — no crossover
        k = [65.0] * 60
        d = [70.0] * 60
        result = self._call_with_stoch(k, d)
        assert result["short"] is False

    def test_no_long_when_k_above_50_despite_crossover(self):
        # K > 50 but crosses up — should NOT trigger long (long requires K < 50)
        k = [60.0] * 58 + [58.0, 62.0]
        d = [60.0] * 58 + [60.0, 60.0]
        result = self._call_with_stoch(k, d)
        assert result["long"] is False

    def test_no_short_when_k_below_50_despite_crossover(self):
        # K < 50 but crosses down — should NOT trigger short (short requires K > 50)
        k = [40.0] * 58 + [42.0, 38.0]
        d = [40.0] * 58 + [40.0, 40.0]
        result = self._call_with_stoch(k, d)
        assert result["short"] is False

    def test_strength_positive_when_long_passes(self):
        k = [10.0] * 58 + [8.0, 12.0]
        d = [10.0] * 58 + [10.0, 10.0]
        result = self._call_with_stoch(k, d)
        assert result["long"] is True
        assert 0.0 < result["strength"] <= 1.0

    def test_strength_higher_for_deeper_oversold(self):
        # K=10 (deep oversold) vs K=45 (mildly oversold) — deep should have higher strength
        k_deep = [10.0] * 58 + [8.0, 12.0]
        d_flat = [10.0] * 58 + [10.0, 10.0]
        result_deep = self._call_with_stoch(k_deep, d_flat)

        k_mild = [45.0] * 58 + [43.0, 47.0]
        d_mild = [44.0] * 58 + [44.0, 44.0]
        result_mild = self._call_with_stoch(k_mild, d_mild)

        if result_deep["long"] and result_mild["long"]:
            assert result_deep["strength"] >= result_mild["strength"]

    def test_error_on_data_unavailable(self):
        with patch("analyzer.fetch_ohlcv", return_value=None):
            result = analyzer.check_rule_6_stoch_rsi("BTC/USDT")
        assert result["error"] is True
        assert result["long"] is False
        assert result["short"] is False

    def test_returns_all_required_fields(self):
        with patch("analyzer.fetch_ohlcv", return_value=None):
            result = analyzer.check_rule_6_stoch_rsi("BTC/USDT")
        for f in (
            "rule",
            "description",
            "long",
            "short",
            "strength",
            "value",
            "signal_hint",
            "error",
        ):
            assert f in result

    def test_fetches_1h_timeframe(self):
        with patch("analyzer.fetch_ohlcv", return_value=None) as mock_fetch:
            analyzer.check_rule_6_stoch_rsi("ETH/USDT")
        assert any("1h" in str(c) for c in mock_fetch.call_args_list), (
            "check_rule_6_stoch_rsi must fetch '1h' candles"
        )

    def test_stoch_none_returns_error(self):
        with patch("analyzer.fetch_ohlcv", return_value=make_ohlcv(60)):
            with patch("analyzer.ta") as mock_ta:
                mock_ta.stochrsi.return_value = None
                result = analyzer.check_rule_6_stoch_rsi("BTC/USDT")
        assert result["error"] is True
        assert result["long"] is False
        assert result["short"] is False

    def test_stoch_missing_expected_columns_returns_error(self):
        with patch("analyzer.fetch_ohlcv", return_value=make_ohlcv(60)):
            with patch("analyzer.ta") as mock_ta:
                mock_ta.stochrsi.return_value = pd.DataFrame({"wrong_col": [1.0] * 60})
                result = analyzer.check_rule_6_stoch_rsi("BTC/USDT")
        assert result["error"] is True
        assert result["long"] is False

    def test_stoch_only_one_valid_row_after_dropna_returns_error(self):
        # After dropna, only 1 row remains — need at least 2 for crossover check
        k_col = "STOCHRSIk_14_14_3_3"
        d_col = "STOCHRSId_14_14_3_3"
        data = pd.DataFrame(
            {
                k_col: [float("nan")] * 59 + [30.0],
                d_col: [float("nan")] * 59 + [30.0],
            }
        )
        with patch("analyzer.fetch_ohlcv", return_value=make_ohlcv(60)):
            with patch("analyzer.ta") as mock_ta:
                mock_ta.stochrsi.return_value = data
                result = analyzer.check_rule_6_stoch_rsi("BTC/USDT")
        assert result["error"] is True
        assert result["long"] is False


# ─── fetch_funding_rate ────────────────────────────────────────────────────────


class TestFetchFundingRate:
    def test_function_exists(self):
        assert hasattr(analyzer, "fetch_funding_rate"), (
            "fetch_funding_rate not found — add it to analyzer.py"
        )

    def test_neutral_rate_not_blocked(self):
        with patch.object(
            analyzer.exchange,
            "fetch_funding_rate",
            return_value={"fundingRate": 0.0001},
        ):
            result = analyzer.fetch_funding_rate("BTC/USDT")
        assert result["rate"] == pytest.approx(0.0001)
        assert result["extreme"] is False
        assert result["blocked_side"] is None

    def test_extreme_positive_blocks_long(self):
        with patch.object(
            analyzer.exchange,
            "fetch_funding_rate",
            return_value={"fundingRate": 0.0006},
        ):
            result = analyzer.fetch_funding_rate("BTC/USDT")
        assert result["extreme"] is True
        assert result["blocked_side"] == "LONG"

    def test_extreme_negative_blocks_short(self):
        with patch.object(
            analyzer.exchange,
            "fetch_funding_rate",
            return_value={"fundingRate": -0.0006},
        ):
            result = analyzer.fetch_funding_rate("BTC/USDT")
        assert result["extreme"] is True
        assert result["blocked_side"] == "SHORT"

    def test_exactly_at_positive_threshold_is_extreme(self):
        # threshold = 0.0005 — at or above is extreme
        with patch.object(
            analyzer.exchange,
            "fetch_funding_rate",
            return_value={"fundingRate": 0.0005},
        ):
            result = analyzer.fetch_funding_rate("BTC/USDT")
        assert result["extreme"] is True
        assert result["blocked_side"] == "LONG"

    def test_exactly_at_negative_threshold_is_extreme(self):
        with patch.object(
            analyzer.exchange,
            "fetch_funding_rate",
            return_value={"fundingRate": -0.0005},
        ):
            result = analyzer.fetch_funding_rate("BTC/USDT")
        assert result["extreme"] is True
        assert result["blocked_side"] == "SHORT"

    def test_just_below_positive_threshold_is_not_extreme(self):
        with patch.object(
            analyzer.exchange,
            "fetch_funding_rate",
            return_value={"fundingRate": 0.0004},
        ):
            result = analyzer.fetch_funding_rate("BTC/USDT")
        assert result["extreme"] is False
        assert result["blocked_side"] is None

    def test_exchange_error_returns_safe_defaults(self):
        with patch.object(
            analyzer.exchange, "fetch_funding_rate", side_effect=Exception("timeout")
        ):
            result = analyzer.fetch_funding_rate("BTC/USDT")
        assert result["rate"] is None
        assert result["extreme"] is False
        assert result["blocked_side"] is None

    def test_returns_all_required_fields(self):
        with patch.object(
            analyzer.exchange,
            "fetch_funding_rate",
            return_value={"fundingRate": 0.0001},
        ):
            result = analyzer.fetch_funding_rate("BTC/USDT")
        for f in ("rate", "extreme", "blocked_side"):
            assert f in result


# ─── analyze() — 6-rule system ────────────────────────────────────────────────


class TestAnalyzeSixRules:
    def run(self, long_flags, short_flags, funding=None):
        with ExitStack() as stack:
            for p in patch_analyze(long_flags, short_flags, funding):
                stack.enter_context(p)
            return analyzer.analyze("BTC/USDT")

    def test_total_rules_is_six(self):
        result = self.run([False] * 6, [False] * 6)
        assert result["total_rules"] == 6

    def test_response_has_six_rule_entries(self):
        result = self.run([False] * 6, [False] * 6)
        assert len(result["rules"]) == 6

    def test_buy_when_all_6_long(self):
        result = self.run([True] * 6, [False] * 6)
        assert result["signal"] == "BUY"
        assert result["long_rules_met"] == 6

    def test_buy_when_5_of_6_long(self):
        result = self.run([True, True, True, True, True, False], [False] * 6)
        assert result["signal"] == "BUY"
        assert result["long_rules_met"] == 5

    def test_wait_when_4_of_6_long(self):
        result = self.run([True, True, True, True, False, False], [False] * 6)
        assert result["signal"] == "WAIT"

    def test_sell_when_5_of_6_short(self):
        result = self.run([False] * 6, [True, True, True, True, True, False])
        assert result["signal"] == "SELL"
        assert result["short_rules_met"] == 5

    def test_wait_when_4_of_6_short(self):
        result = self.run([False] * 6, [True, True, True, True, False, False])
        assert result["signal"] == "WAIT"

    def test_funding_blocks_buy_to_wait(self):
        result = self.run([True] * 6, [False] * 6, funding=BLOCK_LONG)
        assert result["signal"] == "WAIT"
        assert result["funding_blocked"] == "LONG"

    def test_funding_blocks_sell_to_wait(self):
        result = self.run([False] * 6, [True] * 6, funding=BLOCK_SHORT)
        assert result["signal"] == "WAIT"
        assert result["funding_blocked"] == "SHORT"

    def test_funding_block_does_not_affect_already_wait(self):
        # Only 3/6 pass — already WAIT, funding should not change that
        result = self.run(
            [True, True, True, False, False, False], [False] * 6, funding=BLOCK_LONG
        )
        assert result["signal"] == "WAIT"

    def test_signal_blocked_reason_set_when_funding_blocks(self):
        result = self.run([True] * 6, [False] * 6, funding=BLOCK_LONG)
        assert "signal_blocked_reason" in result
        assert result["signal_blocked_reason"]  # not empty

    def test_funding_rate_in_response(self):
        result = self.run([False] * 6, [False] * 6)
        assert "funding_rate" in result
        assert "funding_blocked" in result

    def test_forming_at_4_of_6(self):
        result = self.run([True, True, True, True, False, False], [False] * 6)
        assert result["forming"] is True
        assert result["forming_direction"] == "LONG"

    def test_forming_short_at_4_of_6(self):
        result = self.run([False] * 6, [True, True, True, True, False, False])
        assert result["forming"] is True
        assert result["forming_direction"] == "SHORT"

    def test_no_forming_at_3_of_6(self):
        result = self.run([True, True, True, False, False, False], [False] * 6)
        assert result["forming"] is False

    def test_signal_not_forming_at_5_of_6(self):
        # 5/6 triggers a real BUY signal — forming should be False
        result = self.run([True, True, True, True, True, False], [False] * 6)
        assert result["signal"] == "BUY"
        assert result["forming"] is False

    def test_neutral_funding_does_not_block(self):
        result = self.run([True] * 6, [False] * 6, funding=NEUTRAL_FUNDING)
        assert result["signal"] == "BUY"
        assert not result["funding_blocked"]

    def test_wait_on_tie_when_both_long_and_short_reach_threshold(self):
        # Both long and short hit 5/6 simultaneously — conflict → WAIT
        result = self.run([True] * 5 + [False], [True] * 5 + [False])
        assert result["signal"] == "WAIT"
        assert result["long_rules_met"] == 5
        assert result["short_rules_met"] == 5

    def test_confidence_label_strong_when_score_gte_85(self):
        # All 6 pass with strength=1.0 → confidence = 100% → "Strong"
        with ExitStack() as stack:
            for p in patch_analyze([True] * 6, [False] * 6, strength=1.0):
                stack.enter_context(p)
            result = analyzer.analyze("BTC/USDT")
        assert result["confidence_label"] == "Strong"

    def test_confidence_label_medium_when_score_between_70_and_85(self):
        # All 6 pass with strength=0.75 → confidence = 75% → "Medium"
        with ExitStack() as stack:
            for p in patch_analyze([True] * 6, [False] * 6, strength=0.75):
                stack.enter_context(p)
            result = analyzer.analyze("BTC/USDT")
        assert result["confidence_label"] == "Medium"

    def test_current_price_none_when_fetch_raises(self):
        # fetch_ohlcv raises for the price call → current_price should be None, not crash
        rule_fns = [
            "check_rule_1_trend",
            "check_rule_2_rsi",
            "check_rule_3_macd",
            "check_rule_4_ema_stack",
            "check_rule_5_volume",
            "check_rule_6_stoch_rsi",
        ]
        with ExitStack() as stack:
            for fn in rule_fns:
                stack.enter_context(
                    patch(f"analyzer.{fn}", return_value=make_rule(False, False))
                )
            stack.enter_context(
                patch("analyzer.fetch_funding_rate", return_value=NEUTRAL_FUNDING)
            )
            stack.enter_context(
                patch("analyzer.fetch_ohlcv", side_effect=Exception("network error"))
            )
            result = analyzer.analyze("BTC/USDT")
        assert result["current_price"] is None
