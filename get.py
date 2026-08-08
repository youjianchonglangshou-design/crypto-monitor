"""建立供 ChatGPT 分析使用的 20 日視覺等價 snapshot_ai.json。"""
from __future__ import annotations

import hashlib
import json
from collections import Counter
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable, Optional

import numpy as np
import pandas as pd

from github_sync import sync_snapshot_to_github
from scoring_rules import (
    OPPORTUNITY_ENGINE_VERSION,
    PURPLE2_RULE_VERSION,
    build_long_opportunity,
    build_pattern_flags,
    classify_pattern,
    score_hint,
)
from sector_config import SECTOR_TAGS

TW_TZ = timezone(timedelta(hours=8))
SCHEMA_VERSION = "crypto-monitor-ai-v5-opportunity-geometry-dp2-fib"
GROUP_LIMIT = 20

CHART_SEMANTICS = {
    "window_days": 20,
    "source": "same_20_daily_points_used_by_streamlit_chart",
    "price_axis": "actual_price",
    "bb_formula": "ordinary_daily_close_SMA20_plus_minus_2_population_std",
    "ha_ladder": "daily_heikin_ashi_open_close; yellow=close>open, purple=close<open",
    "ha_vs_midline_pct": "(HA_close-BB_midline)/BB_midline*100",
    "band_width_pct": "(BB_upper-BB_lower)/abs(BB_midline)*100",
    "ha_band_position": "0=lower_band, 0.5=band_center, 1=upper_band; values may be <0 or >1",
    "visual_summary": {
        "recent_5d": "short-term visual geometry",
        "full_20d": "whole displayed chart geometry",
        "midline_direction": "rising/falling/flat",
        "bandwidth_state": "expanding/contracting/stable",
        "expansion_direction": "upward/downward/two_sided/contracting/none",
        "note": "raw chart_20d remains authoritative; summary labels are mechanical aids for AI",
    },
    "long_opportunity": {
        "scope": "long-side entry opportunity only; short-side scoring is intentionally not enabled",
        "stars": "1-5 measures entry opportunity/freshness, NOT bullish trend strength",
        "T0": "latest HA still purple; wait for yellow",
        "T1": "yellow appeared but has not exceeded the active Dynamic Purple-2",
        "T2": "yellow appeared and exceeded the active Dynamic Purple-2",
        "midline_regime": "rising / flat / flattening / falling from recent 5d midline slope; rising threshold is intentionally sensitive to visual upward tilt",
        "near_midline": "adaptive by BB band position around 0.5, not a fixed +/- price percentage",
        "breakout": "requires a real below-to-above midline crossing (or left-censored evidence when the 20d window starts already above) plus a meaningful upper-half push; deep breakdown invalidates the old wave",
        "dynamic_purple2": "v3: compare the ACTIVE right purple V directly against the lowest eligible structural left V in the 20d window. Right V must have its own Purple-2; Fib retracement <=0.618 resets to right Higher-Low, >0.618 keeps left Double-V anchor, new lower low resets right when eligible",
        "engine_version": OPPORTUNITY_ENGINE_VERSION,
        "purple2_rule_version": PURPLE2_RULE_VERSION,
        "one_star_note": "one star is not failure; it can mean mature expansion / do-not-chase or otherwise poor long entry timing",
    },
}

_EMOJI_COLOR = {
    "🟢": "green",
    "🔴": "red",
    "⚫": "flat",
}


def _safe_float(value: Any, default: Optional[float] = None):
    try:
        if value is None or value is pd.NA:
            return default
        result = float(value)
        if np.isnan(result) or np.isinf(result):
            return default
        return result
    except Exception:
        return default


def _round(value: Any, digits: int = 8):
    number = _safe_float(value)
    return None if number is None else round(number, digits)


def _color_name(value: Any) -> str:
    return _EMOJI_COLOR.get(str(value), str(value or "unknown").lower())


def _ha_step_color(open_value: Any, close_value: Any) -> str:
    open_number = _safe_float(open_value)
    close_number = _safe_float(close_value)
    if open_number is None or close_number is None:
        return "unknown"
    if close_number > open_number:
        return "yellow"
    if close_number < open_number:
        return "purple"
    return "flat"


def _format_date(timestamp: Any, fallback: Any) -> str:
    try:
        # Pionex 時戳已在 main.py 加 8 小時，以 UTC 解讀即可得到台灣日期。
        return datetime.fromtimestamp(
            float(timestamp) / 1000.0,
            tz=timezone.utc,
        ).strftime("%m/%d")
    except Exception:
        return str(fallback)


def _build_ladder_history(record: dict[str, Any]) -> list[dict[str, Any]]:
    percentages = list(record.get("_ha_pct_series") or [])
    opens = list(record.get("_ha_opens_last20") or [])
    closes = list(record.get("_ha_closes_last20") or [])
    times = list(record.get("_ha_times_last20") or [])

    history: list[dict[str, Any]] = []
    for index, percentage in enumerate(percentages):
        history.append(
            {
                "date": _format_date(times[index], index) if index < len(times) else str(index),
                "pct": _round(percentage, 6),
                "color": _ha_step_color(
                    opens[index] if index < len(opens) else None,
                    closes[index] if index < len(closes) else None,
                ),
            }
        )
    return history


def _pct_change(start: Any, end: Any) -> Optional[float]:
    start_value = _safe_float(start)
    end_value = _safe_float(end)
    if start_value is None or end_value is None or abs(start_value) < 1e-18:
        return None
    return (end_value - start_value) / abs(start_value) * 100.0


def _trend_metrics(values: list[Any], lookback: int) -> dict[str, Any]:
    cleaned = [_safe_float(value) for value in values]
    cleaned = [value for value in cleaned if value is not None]
    if not cleaned:
        return {
            "days": 0,
            "direction": "unknown",
            "change_pct": None,
            "slope_pct_per_day": None,
        }

    window = cleaned[-min(max(2, lookback), len(cleaned)) :]
    if len(window) < 2:
        return {
            "days": len(window),
            "direction": "flat",
            "change_pct": 0.0,
            "slope_pct_per_day": 0.0,
        }

    change_pct = _pct_change(window[0], window[-1])
    base = abs(float(np.mean(window)))
    if base < 1e-18:
        slope_pct_per_day = 0.0
    else:
        x = np.arange(len(window), dtype=float)
        slope = float(np.polyfit(x, np.asarray(window, dtype=float), 1)[0])
        slope_pct_per_day = slope / base * 100.0

    # 約 0.05%/日以下視為肉眼上的平緩；5 日約 ±0.25%，20 日約 ±0.95%。
    flat_threshold = max(0.25, 0.05 * (len(window) - 1))
    if change_pct is None or abs(change_pct) <= flat_threshold:
        direction = "flat"
    elif change_pct > 0:
        direction = "rising"
    else:
        direction = "falling"

    return {
        "days": len(window),
        "direction": direction,
        "change_pct": _round(change_pct, 6),
        "slope_pct_per_day": _round(slope_pct_per_day, 6),
    }


def _bandwidth_metrics(widths: list[Any], lookback: int) -> dict[str, Any]:
    cleaned = [_safe_float(value) for value in widths]
    cleaned = [value for value in cleaned if value is not None]
    if not cleaned:
        return {
            "days": 0,
            "state": "unknown",
            "start_pct": None,
            "end_pct": None,
            "change_points": None,
            "relative_change_pct": None,
        }

    window = cleaned[-min(max(2, lookback), len(cleaned)) :]
    start = window[0]
    end = window[-1]
    change_points = end - start
    relative_change = _pct_change(start, end)

    # 寬度相對改變 5% 以上才視為明確擴張／收縮，避免每日雜訊被誤判。
    if relative_change is None or abs(relative_change) < 5.0:
        state = "stable"
    elif relative_change > 0:
        state = "expanding"
    else:
        state = "contracting"

    return {
        "days": len(window),
        "state": state,
        "start_pct": _round(start, 6),
        "end_pct": _round(end, 6),
        "change_points": _round(change_points, 6),
        "relative_change_pct": _round(relative_change, 6),
    }


def _build_chart_20d(record: dict[str, Any]) -> list[dict[str, Any]]:
    opens = list(record.get("_ha_opens_last20") or [])
    closes = list(record.get("_ha_closes_last20") or [])
    times = list(record.get("_ha_times_last20") or [])
    midlines = list(record.get("_bb_basis_series") or [])
    uppers = list(record.get("_bb_upper_series") or [])
    lowers = list(record.get("_bb_lower_series") or [])
    percentages = list(record.get("_ha_pct_series") or [])

    count = min(
        20,
        len(opens),
        len(closes),
        len(times),
        len(midlines),
        len(uppers),
        len(lowers),
    )
    if count <= 0:
        return []

    opens = opens[-count:]
    closes = closes[-count:]
    times = times[-count:]
    midlines = midlines[-count:]
    uppers = uppers[-count:]
    lowers = lowers[-count:]
    percentages = percentages[-count:] if percentages else []

    output: list[dict[str, Any]] = []
    for index in range(count):
        ha_open = _safe_float(opens[index])
        ha_close = _safe_float(closes[index])
        midline = _safe_float(midlines[index])
        upper = _safe_float(uppers[index])
        lower = _safe_float(lowers[index])

        ha_vs_midline = (
            _safe_float(percentages[index])
            if index < len(percentages)
            else None
        )
        if ha_vs_midline is None and ha_close is not None and midline:
            ha_vs_midline = (ha_close - midline) / midline * 100.0

        bandwidth_pct = None
        band_position = None
        if (
            upper is not None
            and lower is not None
            and midline is not None
            and abs(midline) > 1e-18
        ):
            bandwidth_pct = (upper - lower) / abs(midline) * 100.0
        if (
            ha_close is not None
            and upper is not None
            and lower is not None
            and abs(upper - lower) > 1e-18
        ):
            # 0=下軌、0.5=通道中心附近、1=上軌；可小於0或大於1。
            band_position = (ha_close - lower) / (upper - lower)

        output.append(
            {
                "date": _format_date(times[index], index),
                "ha_open": _round(ha_open),
                "ha_close": _round(ha_close),
                "ha_color": _ha_step_color(ha_open, ha_close),
                "bb_upper": _round(upper),
                "bb_midline": _round(midline),
                "bb_lower": _round(lower),
                "ha_vs_midline_pct": _round(ha_vs_midline, 6),
                "band_width_pct": _round(bandwidth_pct, 6),
                "ha_band_position": _round(band_position, 6),
            }
        )
    return output


def _position_zone(point: dict[str, Any]) -> str:
    position = _safe_float(point.get("ha_band_position"))
    pct = _safe_float(point.get("ha_vs_midline_pct"))
    if position is None:
        return "unknown"
    if position > 1:
        return "above_upper"
    if position >= 0.75:
        return "upper_quarter"
    if pct is not None and pct >= 0:
        return "above_midline"
    if position <= 0:
        return "below_lower"
    if position <= 0.25:
        return "lower_quarter"
    return "below_midline"


def _visual_window_summary(chart: list[dict[str, Any]], days: int) -> dict[str, Any]:
    if not chart:
        return {"days": 0, "channel": {"state": "unknown", "direction": "unknown"}}

    window = chart[-min(days, len(chart)) :]
    midlines = [point.get("bb_midline") for point in window]
    uppers = [point.get("bb_upper") for point in window]
    lowers = [point.get("bb_lower") for point in window]
    ha_closes = [point.get("ha_close") for point in window]
    widths = [point.get("band_width_pct") for point in window]

    midline = _trend_metrics(midlines, len(window))
    upper = _trend_metrics(uppers, len(window))
    lower = _trend_metrics(lowers, len(window))
    ha = _trend_metrics(ha_closes, len(window))
    bandwidth = _bandwidth_metrics(widths, len(window))

    state = bandwidth.get("state", "unknown")
    if state == "expanding":
        if midline.get("direction") == "rising":
            expansion_direction = "upward"
        elif midline.get("direction") == "falling":
            expansion_direction = "downward"
        else:
            expansion_direction = "two_sided"
    elif state == "contracting":
        expansion_direction = "contracting"
    elif state == "stable":
        expansion_direction = "none"
    else:
        expansion_direction = "unknown"

    return {
        "days": len(window),
        "midline": midline,
        "upper_band": upper,
        "lower_band": lower,
        "ha_ladder": ha,
        "bandwidth": bandwidth,
        "channel": {
            "state": state,
            "direction": midline.get("direction", "unknown"),
            "expansion_direction": expansion_direction,
            "upper_change_pct": upper.get("change_pct"),
            "lower_change_pct": lower.get("change_pct"),
            "midline_change_pct": midline.get("change_pct"),
        },
    }


def _build_visual_summary(chart: list[dict[str, Any]]) -> dict[str, Any]:
    if not chart:
        return {
            "recent_5d": _visual_window_summary([], 5),
            "full_20d": _visual_window_summary([], 20),
            "latest": {},
        }

    latest = chart[-1]
    return {
        "recent_5d": _visual_window_summary(chart, 5),
        "full_20d": _visual_window_summary(chart, 20),
        "latest": {
            "date": latest.get("date"),
            "ha_color": latest.get("ha_color"),
            "ha_vs_midline_pct": latest.get("ha_vs_midline_pct"),
            "ha_band_position": latest.get("ha_band_position"),
            "position_zone": _position_zone(latest),
            "band_width_pct": latest.get("band_width_pct"),
        },
    }


def _four_h_pair(previous: str, current: str) -> str:
    return f"{_color_name(previous)}_{_color_name(current)}"


def _compact_record(source: dict[str, Any]) -> dict[str, Any]:
    history = _build_ladder_history(source)
    chart_20d = _build_chart_20d(source)
    visual_summary = _build_visual_summary(chart_20d)
    flag_history = [
        {
            "date": item["date"],
            "pct_vs_midline": item["pct"],
            "color": item["color"],
        }
        for item in history
    ]
    flags = (
        source.get("_pattern_flags")
        or source.get("pattern_flags")
        or build_pattern_flags(source, flag_history)
    )
    pattern_type = (
        source.get("_pattern_type_hint")
        or source.get("pattern_type_hint")
        or classify_pattern(flags)
    )
    score = source.get("_machine_score_hint_0_100")
    if score is None:
        score = source.get("machine_score_hint_0_100")
    if score is None:
        score = score_hint(flags, {"abs_dev": source.get("_abs_dev")})

    opportunity = (
        source.get("_long_opportunity")
        or source.get("opportunity_long")
        or build_long_opportunity(source, flag_history)
    )

    symbol = str(source.get("幣種") or source.get("symbol") or "").upper()
    threshold = source.get("_ha_threshold") or source.get("ha_color_threshold") or {}
    h4_tail = [_color_name(value) for value in list(source.get("_ha4h_color_series") or [])[-4:]]
    h4_pair = _four_h_pair(source.get("4H前"), source.get("4H當"))

    return {
        "symbol": symbol,
        "sectors": list(SECTOR_TAGS.get(symbol, ["未分類"])),
        "price": _round(source.get("_price")),
        "bb_upper_1d": _round(source.get("_bb_upper_1d")),
        "bb_midline_1d": _round(source.get("_bb1d")),
        "bb_lower_1d": _round(source.get("_bb_lower_1d")),
        "bb_pct": _round(source.get("_bb_pct"), 6),
        "d1_prev": _color_name(source.get("1D前")),
        "d1_curr": _color_name(source.get("1D當")),
        "h4_prev": _color_name(source.get("4H前")),
        "h4_curr": _color_name(source.get("4H當")),
        "h4_tail": h4_tail,
        "threshold": {
            "state": str(threshold.get("state") or "unknown"),
            "price": _round(threshold.get("price")),
            "gap_pct": _round(threshold.get("signed_gap_pct"), 6),
        },
        # 新版主判斷：星級代表「做多進場機會」，不是趨勢強弱。
        "opportunity_long": opportunity,
        # 最近8日階梯摘要保留，方便 AI 快速閱讀；權威資料仍是 chart_20d。
        "ladder_tail": history[-8:],
        # 20 日視覺等價資料：與 Streamlit 圖表使用完全相同的 HA + BB 序列。
        "chart_20d": chart_20d,
        # 人眼會判斷的斜率、擴張/收縮、方向。
        "visual_summary": visual_summary,
        # 舊型態/L2/機械分數只留作歷史對照，不參與新版排序與星級。
        "legacy_reference": {
            "ladder": {
                "state": str(flags.get("ladder_trigger_state") or "red"),
                "label": str(flags.get("ladder_trigger_label") or "Reset"),
                "latest_color": str(flags.get("latest_color") or "unknown"),
                "latest_pct": _round(flags.get("latest_pct_vs_midline"), 6),
                "yellow_run_length": int(flags.get("yellow_run_length") or 0),
                "mature": bool(flags.get("ladder_trigger_mature")),
            },
            "pattern": {
                "type": str(pattern_type),
                "breakout_pullback_restart": bool(flags.get("breakout_pullback_yellow_restart")),
                "po3_quality": str(flags.get("po3_amd_quality_label") or "none"),
                "yellow_over_previous_purple_count": int(flags.get("yellow_over_previous_purple_count") or 0),
                "four_h_trigger": h4_pair,
            },
            "score": int(score or 0),
        },
    }


def _build_breadth(records: list[dict[str, Any]]) -> dict[str, Any]:
    total = len(records)
    latest_colors = Counter(
        (record.get("opportunity_long", {}).get("current", {}) or {}).get("ha_color", "unknown")
        for record in records
    )
    star_counts = Counter(
        int(record.get("opportunity_long", {}).get("stars", 1) or 1)
        for record in records
    )
    stage_counts = Counter(
        record.get("opportunity_long", {}).get("trigger_stage", "T0")
        for record in records
    )
    midline_counts = Counter(
        (record.get("opportunity_long", {}).get("midline", {}) or {}).get("state", "unknown")
        for record in records
    )

    above = sum(1 for record in records if (record.get("bb_pct") or 0) > 0)
    below = sum(1 for record in records if (record.get("bb_pct") or 0) < 0)
    at_midline = total - above - below

    return {
        "long_opportunity": {
            "five_star": int(star_counts.get(5, 0)),
            "four_star": int(star_counts.get(4, 0)),
            "three_star": int(star_counts.get(3, 0)),
            "two_star": int(star_counts.get(2, 0)),
            "one_star": int(star_counts.get(1, 0)),
            "three_star_or_better": int(sum(star_counts.get(x, 0) for x in (3,4,5))),
        },
        "trigger_stage": {
            "T0": int(stage_counts.get("T0", 0)),
            "T1": int(stage_counts.get("T1", 0)),
            "T2": int(stage_counts.get("T2", 0)),
        },
        "midline_regime": {
            "rising": int(midline_counts.get("rising", 0)),
            "flat": int(midline_counts.get("flat", 0)),
            "flattening": int(midline_counts.get("flattening", 0)),
            "falling": int(midline_counts.get("falling", 0)),
        },
        "daily_ha": {
            "purple": int(latest_colors.get("purple", 0)),
            "yellow": int(latest_colors.get("yellow", 0)),
            "flat_or_unknown": int(total-latest_colors.get("purple",0)-latest_colors.get("yellow",0)),
        },
        "midline_position": {
            "real_price_above": above,
            "real_price_below": below,
            "real_price_at": at_midline,
            "real_price_near_3pct": sum(1 for r in records if r.get("bb_pct") is not None and abs(r.get("bb_pct") or 0) <= 3),
            "ha_near_midline_adaptive": sum(
                1 for r in records
                if bool(((r.get("opportunity_long", {}) or {}).get("current", {}) or {}).get("near_midline"))
            ),
        },
    }

def _ranked_symbols(
    records: list[dict[str, Any]],
    predicate,
    *,
    limit: int = GROUP_LIMIT,
) -> list[str]:
    selected = [record for record in records if predicate(record)]
    def key(record):
        opp = record.get("opportunity_long", {}) or {}
        stars = int(opp.get("stars", 1) or 1)
        stage = str(opp.get("trigger_stage", "T0"))
        days = (opp.get("trigger_freshness", {}) or {}).get("days_ago")
        fresh = 9 if days is None else int(days)
        current_pct = abs(float((opp.get("current", {}) or {}).get("ha_vs_midline_pct") or 999))
        return (-stars, {"T2":0,"T1":1,"T0":2}.get(stage,3), fresh, current_pct, record.get("symbol") or "")
    selected.sort(key=key)
    return [str(record.get("symbol")) for record in selected[:limit]]


def _build_groups(records: list[dict[str, Any]]) -> dict[str, list[str]]:
    def stars(n):
        return lambda r: int((r.get("opportunity_long", {}) or {}).get("stars", 1) or 1) == n
    def setup_ids(*ids):
        wanted=set(ids)
        return lambda r: int((r.get("opportunity_long", {}) or {}).get("setup_id",0) or 0) in wanted
    return {
        "long_5_star_triggered": _ranked_symbols(records, stars(5)),
        "long_4_star_confirming": _ranked_symbols(records, stars(4)),
        "long_3_star_waiting": _ranked_symbols(records, stars(3)),
        "wave3_midline_retest": _ranked_symbols(records, setup_ids(1,2,3,9)),
        "below_midline_reversal": _ranked_symbols(records, setup_ids(4,5,11)),
        "midline_chop": _ranked_symbols(records, setup_ids(6)),
        "first_midline_test": _ranked_symbols(records, setup_ids(7)),
        "extreme_squeeze": _ranked_symbols(records, setup_ids(10)),
        "mature_expansion_do_not_chase": _ranked_symbols(
            records,
            lambda r: bool(((r.get("opportunity_long", {}) or {}).get("maturity", {}) or {}).get("mature_bull_expansion"))
            or bool(((r.get("opportunity_long", {}) or {}).get("maturity", {}) or {}).get("mature_bear_expansion")),
        ),
        "natural_midline_attack": _ranked_symbols(records, setup_ids(7)),
        "moved_away_from_midline_sweet_zone": _ranked_symbols(
            records,
            lambda r: "離開中軌甜蜜區" in str((r.get("opportunity_long", {}) or {}).get("setup_name", ""))
            or "剩餘肉量下降" in str((r.get("opportunity_long", {}) or {}).get("structure_state", "")),
        ),
        "dynamic_purple2_left_anchor": _ranked_symbols(
            records,
            lambda r: ((r.get("opportunity_long", {}) or {}).get("purple_structure", {}) or {}).get("anchor_source") == "prior_left_v",
        ),
        "dynamic_purple2_right_anchor": _ranked_symbols(
            records,
            lambda r: ((r.get("opportunity_long", {}) or {}).get("purple_structure", {}) or {}).get("anchor_source") == "active_right_v",
        ),
        "midline_long_friendly": _ranked_symbols(
            records,
            lambda r: ((r.get("opportunity_long", {}) or {}).get("midline", {}) or {}).get("state") in {"rising","flat","flattening"},
        ),
    }

def _snapshot_hash(selection: str, records: list[dict[str, Any]]) -> str:
    raw = json.dumps(
        {
            "schema_version": SCHEMA_VERSION,
            "selection": selection,
            "records": records,
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def build_snapshot_payload(
    df,
    plot_results: Iterable[dict[str, Any]],
    selection: str = "—",
    sort_option: str = "—",
    title: str = "HA Crypto Terminal",
    generated_at: Optional[str] = None,
):
    del df  # 保留舊函式介面，避免 main.py 呼叫方式改動。
    del title

    records = sorted(
        (_compact_record(record) for record in list(plot_results)),
        key=lambda record: record.get("symbol") or "",
    )
    generated_time = generated_at or datetime.now(TW_TZ).strftime("%Y-%m-%d %H:%M:%S")

    payload = {
        "batch": {
            "generated_at_taiwan": generated_time,
            "snapshot_hash": _snapshot_hash(selection, records),
            "schema_version": SCHEMA_VERSION,
            "engine_version": OPPORTUNITY_ENGINE_VERSION,
            "purple2_rule_version": PURPLE2_RULE_VERSION,
            "count": len(records),
            "selection": selection,
            "sort_option": sort_option,
        },
        "chart_semantics": CHART_SEMANTICS,
        "breadth": _build_breadth(records),
        "groups": _build_groups(records),
        "records": records,
    }

    sync_snapshot_to_github(payload)
    return payload
