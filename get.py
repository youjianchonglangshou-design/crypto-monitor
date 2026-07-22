"""建立供 ChatGPT 分析使用的精簡 snapshot_ai.json。"""
from __future__ import annotations

import hashlib
import json
from collections import Counter
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable, Optional

import numpy as np
import pandas as pd

from github_sync import sync_snapshot_to_github
from scoring_rules import build_pattern_flags, classify_pattern, score_hint
from sector_config import SECTOR_TAGS

TW_TZ = timezone(timedelta(hours=8))
SCHEMA_VERSION = "crypto-monitor-ai-v1"
GROUP_LIMIT = 20

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


def _four_h_pair(previous: str, current: str) -> str:
    return f"{_color_name(previous)}_{_color_name(current)}"


def _compact_record(source: dict[str, Any]) -> dict[str, Any]:
    history = _build_ladder_history(source)
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

    symbol = str(source.get("幣種") or source.get("symbol") or "").upper()
    threshold = source.get("_ha_threshold") or source.get("ha_color_threshold") or {}
    h4_tail = [_color_name(value) for value in list(source.get("_ha4h_color_series") or [])[-4:]]
    h4_pair = _four_h_pair(source.get("4H前"), source.get("4H當"))

    return {
        "symbol": symbol,
        "sectors": list(SECTOR_TAGS.get(symbol, ["未分類"])),
        "price": _round(source.get("_price")),
        "bb_midline_1d": _round(source.get("_bb1d")),
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
            "breakout_pullback_restart": bool(
                flags.get("breakout_pullback_yellow_restart")
            ),
            "po3_quality": str(flags.get("po3_amd_quality_label") or "none"),
            "po3_strong": bool(flags.get("po3_amd_strong_reversal")),
            "po3_candidate": bool(flags.get("po3_amd_w_bottom_candidate")),
            "po3_early": bool(flags.get("po3_amd_early_weak_rebound")),
            "yellow_over_previous_purple_count": int(
                flags.get("yellow_over_previous_purple_count") or 0
            ),
            "four_h_trigger": h4_pair,
        },
        "score": int(score or 0),
        "ladder_tail": history[-8:],
    }


def _build_breadth(records: list[dict[str, Any]]) -> dict[str, Any]:
    total = len(records)

    ladder_counts = Counter(
        record.get("ladder", {}).get("state", "unknown") for record in records
    )
    daily_counts = Counter(
        record.get("threshold", {}).get("state", "unknown") for record in records
    )
    four_h_counts = Counter(
        record.get("pattern", {}).get("four_h_trigger", "unknown") for record in records
    )

    above = sum(1 for record in records if (record.get("bb_pct") or 0) > 0)
    below = sum(1 for record in records if (record.get("bb_pct") or 0) < 0)
    at_midline = total - above - below
    near_1 = sum(
        1
        for record in records
        if record.get("bb_pct") is not None and abs(record["bb_pct"]) <= 1
    )
    near_3 = sum(
        1
        for record in records
        if record.get("bb_pct") is not None and abs(record["bb_pct"]) <= 3
    )

    red_count = int(ladder_counts.get("red", 0))
    red_ratio = round(red_count / total * 100, 2) if total else 0.0
    red_majority = red_count > total / 2 if total else False

    return {
        "ladder": {
            "red": red_count,
            "yellow": int(ladder_counts.get("yellow", 0)),
            "green": int(ladder_counts.get("green", 0)),
            "other": int(
                total
                - ladder_counts.get("red", 0)
                - ladder_counts.get("yellow", 0)
                - ladder_counts.get("green", 0)
            ),
            "red_ratio_pct": red_ratio,
            "red_majority": red_majority,
        },
        "daily_ha": {
            "purple": int(daily_counts.get("purple", 0)),
            "yellow": int(daily_counts.get("yellow", 0)),
            "flat_or_unknown": int(
                total
                - daily_counts.get("purple", 0)
                - daily_counts.get("yellow", 0)
            ),
        },
        "four_h_pairs": {
            "red_red": int(four_h_counts.get("red_red", 0)),
            "red_green": int(four_h_counts.get("red_green", 0)),
            "green_green": int(four_h_counts.get("green_green", 0)),
            "green_red": int(four_h_counts.get("green_red", 0)),
            "other": int(
                total
                - four_h_counts.get("red_red", 0)
                - four_h_counts.get("red_green", 0)
                - four_h_counts.get("green_green", 0)
                - four_h_counts.get("green_red", 0)
            ),
        },
        "midline": {
            "above": above,
            "below": below,
            "at": at_midline,
            "near_1pct": near_1,
            "near_3pct": near_3,
        },
        "warnings": (
            ["ladder_red_majority_broad_market_pullback"]
            if red_majority
            else []
        ),
    }


def _ranked_symbols(
    records: list[dict[str, Any]],
    predicate,
    *,
    near_first: bool = False,
    limit: int = GROUP_LIMIT,
) -> list[str]:
    selected = [record for record in records if predicate(record)]

    if near_first:
        selected.sort(
            key=lambda record: (
                abs(record["bb_pct"]) if record.get("bb_pct") is not None else 999,
                -int(record.get("score") or 0),
                record.get("symbol") or "",
            )
        )
    else:
        selected.sort(
            key=lambda record: (
                -int(record.get("score") or 0),
                abs(record["bb_pct"]) if record.get("bb_pct") is not None else 999,
                record.get("symbol") or "",
            )
        )
    return [str(record.get("symbol")) for record in selected[:limit]]


def _build_groups(records: list[dict[str, Any]]) -> dict[str, list[str]]:
    return {
        "breakout_pullback_restart": _ranked_symbols(
            records,
            lambda record: bool(
                record.get("pattern", {}).get("breakout_pullback_restart")
            ),
        ),
        "yellow_stage_1": _ranked_symbols(
            records,
            lambda record: (
                record.get("ladder", {}).get("latest_color") == "yellow"
                and record.get("ladder", {}).get("yellow_run_length") == 1
            ),
        ),
        "yellow_stage_2": _ranked_symbols(
            records,
            lambda record: (
                record.get("ladder", {}).get("latest_color") == "yellow"
                and record.get("ladder", {}).get("yellow_run_length") == 2
            ),
        ),
        "four_h_red_green": _ranked_symbols(
            records,
            lambda record: (
                record.get("pattern", {}).get("four_h_trigger") == "red_green"
            ),
        ),
        "four_h_green_green": _ranked_symbols(
            records,
            lambda record: (
                record.get("pattern", {}).get("four_h_trigger") == "green_green"
            ),
        ),
        "near_midline": _ranked_symbols(
            records,
            lambda record: (
                record.get("bb_pct") is not None
                and abs(record.get("bb_pct") or 0) <= 3
            ),
            near_first=True,
        ),
        "ladder_green": _ranked_symbols(
            records,
            lambda record: record.get("ladder", {}).get("state") == "green",
        ),
        "ladder_yellow": _ranked_symbols(
            records,
            lambda record: record.get("ladder", {}).get("state") == "yellow",
        ),
        "po3_strong": _ranked_symbols(
            records,
            lambda record: bool(record.get("pattern", {}).get("po3_strong")),
        ),
        "po3_candidate": _ranked_symbols(
            records,
            lambda record: bool(record.get("pattern", {}).get("po3_candidate")),
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
            "count": len(records),
            "selection": selection,
            "sort_option": sort_option,
        },
        "breadth": _build_breadth(records),
        "groups": _build_groups(records),
        "records": records,
    }

    sync_snapshot_to_github(payload)
    return payload
