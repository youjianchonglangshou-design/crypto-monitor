"""Heikin-Ashi 黃／紫切換分界價。

比較來源固定為普通 K close，不可使用 HA close。
公式完全對應使用者 Pine Script 的三段式高低點邏輯。
"""
from __future__ import annotations
from typing import Any, Optional


def _safe_float(value: Any, default: Optional[float] = None) -> Optional[float]:
    try:
        v = float(value)
        if v != v or v in (float("inf"), float("-inf")):
            return default
        return v
    except Exception:
        return default


def calculate_ha_color_threshold(raw_open: Any, raw_high: Any, raw_low: Any, ha_open: Any):
    o, h, l, hao = map(_safe_float, (raw_open, raw_high, raw_low, ha_open))
    if None in (o, h, l, hao):
        return None, "invalid"
    ha_close_at_current_low = (o + h + 2.0 * l) / 4.0
    ha_close_at_current_high = (o + 2.0 * h + l) / 4.0
    if hao <= ha_close_at_current_low:
        threshold = (4.0 * hao - o - h) / 2.0
        branch = "below_current_low"
    elif hao >= ha_close_at_current_high:
        threshold = (4.0 * hao - o - l) / 2.0
        branch = "above_current_high"
    else:
        threshold = 4.0 * hao - o - h - l
        branch = "inside_current_range"
    if threshold <= 0:
        return None, "invalid"
    return float(threshold), branch


def compute_threshold_from_daily_data(*, daily_raw_candle: dict, daily_ha_open: Any, ordinary_close: Any, timeframe_basis="1D", precision=8) -> dict:
    threshold, branch = calculate_ha_color_threshold(
        daily_raw_candle.get("open"), daily_raw_candle.get("high"), daily_raw_candle.get("low"), daily_ha_open
    )
    close = _safe_float(ordinary_close)
    if threshold is None or close is None:
        return {
            "timeframe_basis": timeframe_basis, "comparison_price_source": "ordinary_k_close", "price": None,
            "state": "unknown", "state_emoji": "—", "signed_gap_pct": None, "absolute_gap_pct": None,
            "switch_direction": "unknown", "switch_condition": None,
            "meaning": "資料不足，無法判定均K分界價。", "calculation_branch": branch,
        }
    threshold = round(threshold, precision)
    gap = round((close - threshold) / threshold * 100.0, precision)
    if close > threshold:
        state, emoji, direction = "yellow", "🟡", "down_to_purple"
        condition = f"ordinary_close < {threshold}"
        meaning = f"目前黃線主導；普通K close跌破{threshold}後轉紫"
    elif close < threshold:
        state, emoji, direction = "purple", "🟣", "up_to_yellow"
        condition = f"ordinary_close > {threshold}"
        meaning = f"目前紫線主導；普通K close突破{threshold}後轉黃"
    else:
        state, emoji, direction = "flat", "⚫", "edge_flip"
        condition = f"ordinary_close == {threshold}"
        meaning = f"目前普通K close正好位於均K分界{threshold}。"
    return {
        "timeframe_basis": timeframe_basis, "comparison_price_source": "ordinary_k_close", "price": threshold,
        "state": state, "state_emoji": emoji, "signed_gap_pct": gap, "absolute_gap_pct": abs(gap),
        "switch_direction": direction, "switch_condition": condition, "meaning": meaning,
        "calculation_branch": branch,
    }
