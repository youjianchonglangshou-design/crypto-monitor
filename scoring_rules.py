"""HA 階梯型態旗標、型態名稱與機械分數。

本地版保留正式 snapshot 使用的欄位名稱、三燈語意及分數封頂。
"""
from __future__ import annotations
from typing import Any


def _f(v: Any, default=0.0) -> float:
    try:
        return float(v)
    except Exception:
        return float(default)


def _round(v, n=6):
    return round(_f(v), n)


def _transition_count(colors: list[str]) -> int:
    return sum(1 for a, b in zip(colors, colors[1:]) if a != b)


def _current_run(history: list[dict]) -> dict:
    if not history:
        return {"color": "unknown", "start_index": 0, "length": 0}
    color = history[-1].get("color", "unknown")
    i = len(history) - 1
    while i > 0 and history[i - 1].get("color") == color:
        i -= 1
    return {"color": color, "start_index": i, "length": len(history) - i}


def _build_ladder_trigger_light(latest_color: str, yellow_run_length: int, r: dict) -> dict:
    series = list(r.get("_ha4h_color_series") or [])
    current_pair_red_green = len(series) >= 2 and series[-2:] == ["🔴", "🟢"]
    current_pair_green_green = len(series) >= 2 and series[-2:] == ["🟢", "🟢"]
    previous_pair_red_green = len(series) >= 3 and series[-3:-1] == ["🔴", "🟢"]
    green_extension_after_rg = current_pair_green_green and previous_pair_red_green
    is_yellow = latest_color == "yellow"
    mature = bool(is_yellow and yellow_run_length >= 2)

    if mature and (current_pair_red_green or green_extension_after_rg):
        state = "green"
        label = "L2+ 啟動" if current_pair_red_green else "L2+ 延續"
    elif mature:
        state = "yellow"
        if r.get("4H前") == "🟢" and r.get("4H當") == "🔴":
            label = "L2+ 轉弱"
        elif current_pair_green_green:
            label = "L2+ 綠綠未觸發"
        else:
            label = "L2+ 待4H"
    else:
        state = "red"
        label = "L1 未成熟" if is_yellow and yellow_run_length == 1 else "Reset"

    return {
        "ladder_trigger_state": state,
        "ladder_trigger_label": label,
        "ladder_trigger_light": state,
        "ladder_trigger_active": state == "green",
        "yellow_run_length": yellow_run_length,
        "ladder_trigger_mature": mature,
        "current_4h_pair_red_green": current_pair_red_green,
        "current_4h_pair_green_green": current_pair_green_green,
        "previous_4h_pair_red_green": previous_pair_red_green,
        "green_extension_after_red_green": green_extension_after_rg,
        "four_h_color_series_tail": series[-6:],
    }


def build_pattern_flags(r: dict, ladder_history: list[dict]) -> dict:
    ready = len(ladder_history) >= 5
    latest = ladder_history[-1] if ladder_history else {}
    latest_color = latest.get("color", "unknown")
    latest_pct = _f(latest.get("pct_vs_midline"), 0.0)
    run = _current_run(ladder_history)
    start = int(run.get("start_index", 0))
    yellow_run_length = run["length"] if latest_color == "yellow" else 0
    light = _build_ladder_trigger_light(latest_color, yellow_run_length, r)

    before = ladder_history[:start]
    had_yellow_above = any(x.get("color") == "yellow" and _f(x.get("pct_vs_midline")) >= 0 for x in before)
    had_any_above = any(_f(x.get("pct_vs_midline")) >= 0 for x in before)
    recent_before = before[-8:]
    recent_above = any(_f(x.get("pct_vs_midline")) >= 0 for x in recent_before)
    bars_since_last_above = None
    for idx in range(len(ladder_history) - 2, -1, -1):
        if _f(ladder_history[idx].get("pct_vs_midline")) >= 0:
            bars_since_last_above = len(ladder_history) - 1 - idx
            break

    prev_run = []
    if start > 0:
        prev_color = ladder_history[start - 1].get("color")
        j = start - 1
        while j >= 0 and ladder_history[j].get("color") == prev_color:
            prev_run.append(ladder_history[j])
            j -= 1
        prev_run.reverse()
    prev_purple_run = prev_run if prev_run and prev_run[-1].get("color") == "purple" else []
    purple_near = bool(prev_purple_run and any(abs(_f(x.get("pct_vs_midline"))) <= 3.0 for x in prev_purple_run))
    purple_not_deep = bool(prev_purple_run and min(_f(x.get("pct_vs_midline")) for x in prev_purple_run) >= -5.0)
    breakout_restart = bool(latest_color == "yellow" and had_yellow_above and purple_near and purple_not_deep)

    previous_purples = [x for x in before if x.get("color") == "purple"][-3:]
    previous_purple_pcts = [_round(x.get("pct_vs_midline")) for x in previous_purples]
    yellow_ref = _f(ladder_history[start].get("pct_vs_midline"), latest_pct) if latest_color == "yellow" else _f(next((x.get("pct_vs_midline") for x in reversed(before) if x.get("color") == "yellow"), latest_pct))
    over_count = sum(1 for x in previous_purple_pcts if yellow_ref > x)

    colors8 = [x.get("color") for x in ladder_history[-8:]]
    colors6 = [x.get("color") for x in ladder_history[-6:]]
    colors5 = [x.get("color") for x in ladder_history[-5:]]
    transitions8 = _transition_count(colors8)
    transitions6 = _transition_count(colors6)
    transitions5 = _transition_count(colors5)
    recent_yellow = sum(c == "yellow" for c in colors8)
    recent_purple = sum(c == "purple" for c in colors8)

    previous_step = _f(ladder_history[-2].get("pct_vs_midline"), latest_pct) if len(ladder_history) >= 2 else latest_pct
    first_run_pct = _f(ladder_history[start].get("pct_vs_midline"), latest_pct)
    lift_previous = latest_pct - previous_step
    run_lift = latest_pct - first_run_pct
    if previous_purple_pcts:
        margins = [latest_pct - p for p in previous_purple_pcts]
        avg_margin = sum(margins) / len(margins)
        max_margin = max(margins)
        min_margin = min(margins)
        rebound_low = latest_pct - min(previous_purple_pcts)
    else:
        avg_margin = max_margin = min_margin = rebound_low = 0.0

    below_candidate = bool(latest_color == "yellow" and latest_pct < 0 and over_count >= 2)
    clean_fast = bool(below_candidate and yellow_run_length <= 3 and transitions6 <= 1)
    interrupted = transitions6 >= 2
    rapid = bool(rebound_low >= 3.0 or run_lift >= 3.0)
    strong = bool(below_candidate and over_count >= 2 and clean_fast and rapid)
    w_bottom = bool(below_candidate and not strong and over_count >= 2 and (interrupted or yellow_run_length >= 2))
    early = bool(latest_color == "yellow" and latest_pct < 0 and yellow_run_length == 1 and over_count >= 1 and rebound_low < 3.0)
    quality = "strong_fast_reclaim" if strong else ("w_bottom_candidate" if w_bottom else ("early_weak_rebound" if early else "none"))

    four_h_rg = r.get("4H前") == "🔴" and r.get("4H當") == "🟢"
    four_h_gg = r.get("4H前") == "🟢" and r.get("4H當") == "🟢"
    four_h_label = "4H前紅→4H當綠：最佳啟動" if four_h_rg else ("4H綠→綠：偏多延續" if four_h_gg else "4H未啟動或偏弱")

    flags = {
        **light,
        "analysis_ready": ready,
        "latest_color": latest_color,
        "latest_color_emoji": {"yellow": "🟡", "purple": "🟣", "flat": "⚫"}.get(latest_color, "—"),
        "latest_pct_vs_midline": _round(latest_pct),
        "latest_above_midline": latest_pct >= 0,
        "latest_near_midline": abs(latest_pct) <= 3.0,
        "current_color_run": run,
        "had_yellow_above_midline_before_current_run": had_yellow_above,
        "had_any_above_midline_before_current_run": had_any_above,
        "recent_above_midline_before_current_run": recent_above,
        "bars_since_last_above_midline": bars_since_last_above,
        "prior_breakout_then_pullback_reclaim": bool(latest_color == "yellow" and latest_pct >= 0 and had_any_above and start > 0),
        "structurally_suppressed_never_touched_midline": not any(_f(x.get("pct_vs_midline")) >= 0 for x in ladder_history),
        "purple_pullback_near_midline_after_breakout": purple_near,
        "purple_pullback_not_deep_broken": purple_not_deep,
        "breakout_pullback_yellow_restart": breakout_restart,
        "previous_purple_pcts_for_po3": previous_purple_pcts,
        "yellow_ref_pct_for_po3": _round(yellow_ref),
        "yellow_over_previous_purple_count": over_count,
        "yellow_over_2_previous_purple_steps": over_count >= 2,
        "yellow_over_3_previous_purple_steps": over_count >= 3,
        "below_midline_po3_amd_candidate": below_candidate,
        "po3_amd_quality_label": quality,
        "po3_amd_strong_reversal": strong,
        "po3_amd_w_bottom_candidate": w_bottom,
        "po3_amd_early_weak_rebound": early,
        "recent_color_transitions_8d": transitions8,
        "recent_color_transitions_6d": transitions6,
        "recent_color_transitions_5d": transitions5,
        "clean_fast_reclaim_run": clean_fast,
        "interrupted_reclaim_by_color_mix": interrupted,
        "rapid_reclaim_magnitude": rapid,
        "strong_reclaim_run_length_days": run.get("length", 0),
        "recent_yellow_count_8d": recent_yellow,
        "recent_purple_count_8d": recent_purple,
        "lift_from_previous_step_pct": _round(lift_previous),
        "current_yellow_run_lift_pct": _round(run_lift),
        "avg_reclaim_margin_vs_prev3_purple_pct": _round(avg_margin),
        "max_reclaim_margin_vs_prev3_purple_pct": _round(max_margin),
        "min_reclaim_margin_vs_prev3_purple_pct": _round(min_margin),
        "rebound_from_recent_purple_low_pct": _round(rebound_low),
        "four_h_red_to_green": four_h_rg,
        "four_h_green_green": four_h_gg,
        "four_h_trigger_label": four_h_label,
    }
    return flags


def classify_pattern(flags: dict) -> str:
    if flags.get("breakout_pullback_yellow_restart"):
        return "中軌突破回踩轉黃型"
    if flags.get("po3_amd_strong_reversal"):
        return "中軌下方 PO3/AMD 強反轉型"
    if flags.get("po3_amd_w_bottom_candidate"):
        return "中軌下方 PO3/AMD 反轉候選型"
    if flags.get("po3_amd_early_weak_rebound"):
        return "中軌下方 PO3/AMD 轉黃早期觀察型"
    if flags.get("latest_color") == "yellow" and flags.get("latest_near_midline"):
        return "中軌附近磨合轉黃型"
    if flags.get("latest_color") == "purple":
        return "紫線未轉黃觀察型"
    return "一般觀察型"


def score_hint(flags: dict, item: dict) -> int:
    pattern = classify_pattern(flags)
    latest = _f(flags.get("latest_pct_vs_midline"))
    abs_dev = abs(_f(item.get("abs_dev", item.get("_abs_dev", 999))))
    over = int(flags.get("yellow_over_previous_purple_count") or 0)
    rg = bool(flags.get("four_h_red_to_green"))
    gg = bool(flags.get("four_h_green_green"))
    near = abs(latest) <= 3
    above = latest >= 0

    if pattern == "中軌突破回踩轉黃型":
        score = 76 + (10 if near else 0) + (8 if above else 0) + (2 if over >= 2 else 0) + (4 if rg else 0)
        if latest < 0: score = min(score, 80)
        if not rg and not gg: score = min(score, 90)
        if abs_dev > 7: score = min(score, 76)
        elif abs_dev > 5: score = min(score, 82)
        elif abs_dev > 3: score = min(score, 90)
        return max(0, min(100, int(score)))

    if pattern == "中軌下方 PO3/AMD 強反轉型":
        score = 66 + (8 if over >= 3 else 4) + (8 if flags.get("rapid_reclaim_magnitude") else 0) + (6 if rg else 3 if gg else 0)
        return min(88, int(score))

    if pattern == "中軌下方 PO3/AMD 反轉候選型":
        score = 52 + (14 if over >= 3 else 8) + (8 if flags.get("rapid_reclaim_magnitude") else 0) + (8 if rg else 4 if gg else 0) + (4 if near else 0)
        return min(80, int(score))

    if pattern == "中軌下方 PO3/AMD 轉黃早期觀察型":
        score = 36 + (8 if rg else 4 if gg else 0) + (6 if near else 0) + (4 if over >= 2 else 0)
        return min(55, int(score))

    if pattern == "中軌附近磨合轉黃型":
        score = 58 + (10 if near else 0) + (8 if above else 0) + (8 if rg else 4 if gg else 0)
        return min(84, int(score))

    if pattern == "紫線未轉黃觀察型":
        score = 0
        if abs(latest) <= 3: score += 18
        if abs(latest) <= 1: score += 6
        if rg: score += 18
        elif gg: score += 8
        if latest >= 0: score += 6
        return min(42, int(score))

    score = 14
    if flags.get("latest_color") == "yellow": score += 18
    if near: score += 15
    if above: score += 10
    if rg: score += 12
    elif gg: score += 8
    return min(75, int(score))
