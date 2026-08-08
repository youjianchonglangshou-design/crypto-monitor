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

# ==================== Opportunity Geometry（做多機會掃描） ====================
# 星級只代表「現在還有多少做多進場價值」，不是趨勢強弱。
# 因此成熟多頭與成熟空頭都可能只有 ★：前者不追漲，後者不追跌也不摸底。

LONG_NEAR_MIDLINE_PCT = 3.0
LONG_BREAKOUT_PCT = 2.5
MIDLINE_FLAT_SLOPE_PCT_PER_DAY = 0.25
MIDLINE_FLATTENING_MAX_FALL_PCT_PER_DAY = -0.65


def _opportunity_points(r: dict) -> list[dict[str, Any]]:
    """從 main.py 的 20 日原始序列，或 snapshot chart_20d，建立統一幾何點。"""
    existing = r.get("chart_20d")
    if isinstance(existing, list) and existing:
        out = []
        for idx, point in enumerate(existing[-20:]):
            out.append({
                "index": idx,
                "date": str(point.get("date") or idx),
                "open": _f(point.get("ha_open")),
                "close": _f(point.get("ha_close")),
                "color": str(point.get("ha_color") or "unknown"),
                "pct": _f(point.get("ha_vs_midline_pct")),
                "mid": _f(point.get("bb_midline")),
                "upper": _f(point.get("bb_upper")),
                "lower": _f(point.get("bb_lower")),
                "width": _f(point.get("band_width_pct")),
                "band_pos": _f(point.get("ha_band_position"), 0.5),
            })
        return out

    opens = list(r.get("_ha_opens_last20") or [])
    closes = list(r.get("_ha_closes_last20") or [])
    pcts = list(r.get("_ha_pct_series") or [])
    mids = list(r.get("_bb_basis_series") or [])
    uppers = list(r.get("_bb_upper_series") or [])
    lowers = list(r.get("_bb_lower_series") or [])
    times = list(r.get("_ha_times_last20") or [])
    count = min(20, len(opens), len(closes), len(pcts), len(mids), len(uppers), len(lowers))
    if count <= 0:
        return []
    starts = [len(opens)-count, len(closes)-count, len(pcts)-count, len(mids)-count, len(uppers)-count, len(lowers)-count]
    opens = opens[starts[0]:]
    closes = closes[starts[1]:]
    pcts = pcts[starts[2]:]
    mids = mids[starts[3]:]
    uppers = uppers[starts[4]:]
    lowers = lowers[starts[5]:]
    times = times[-count:] if times else list(range(count))

    out = []
    for idx in range(count):
        open_v = _f(opens[idx])
        close_v = _f(closes[idx])
        upper_v = _f(uppers[idx])
        lower_v = _f(lowers[idx])
        mid_v = _f(mids[idx])
        color = "yellow" if close_v > open_v else "purple" if close_v < open_v else "flat"
        width = ((upper_v-lower_v)/abs(mid_v)*100.0) if abs(mid_v) > 1e-18 else 0.0
        band_pos = ((close_v-lower_v)/(upper_v-lower_v)) if abs(upper_v-lower_v) > 1e-18 else 0.5
        try:
            from datetime import datetime, timezone
            date_text = datetime.fromtimestamp(float(times[idx])/1000.0, tz=timezone.utc).strftime("%m/%d")
        except Exception:
            date_text = str(idx)
        out.append({
            "index": idx,
            "date": date_text,
            "open": open_v,
            "close": close_v,
            "color": color,
            "pct": _f(pcts[idx]),
            "mid": mid_v,
            "upper": upper_v,
            "lower": lower_v,
            "width": width,
            "band_pos": band_pos,
        })
    return out


def _slope_pct_per_day(values: list[float]) -> float:
    vals = [_f(v) for v in values]
    if len(vals) < 2:
        return 0.0
    mean = sum(vals) / len(vals)
    if abs(mean) < 1e-18:
        return 0.0
    n = len(vals)
    x_mean = (n - 1) / 2.0
    denom = sum((i - x_mean) ** 2 for i in range(n))
    if denom <= 0:
        return 0.0
    slope = sum((i - x_mean) * (vals[i] - mean) for i in range(n)) / denom
    return slope / abs(mean) * 100.0


def _midline_regime(points: list[dict[str, Any]]) -> dict[str, Any]:
    mids = [_f(p.get("mid")) for p in points]
    recent = mids[-5:]
    previous = mids[-10:-5] if len(mids) >= 10 else mids[:-5]
    recent_slope = _slope_pct_per_day(recent)
    previous_slope = _slope_pct_per_day(previous) if len(previous) >= 2 else recent_slope
    improvement = recent_slope - previous_slope

    if recent_slope >= MIDLINE_FLAT_SLOPE_PCT_PER_DAY:
        state, symbol, label = "rising", "↑", "上斜"
    elif recent_slope > -MIDLINE_FLAT_SLOPE_PCT_PER_DAY:
        state, symbol, label = "flat", "→", "平緩"
    elif (
        recent_slope >= MIDLINE_FLATTENING_MAX_FALL_PCT_PER_DAY
        and previous_slope < recent_slope - 0.18
    ):
        state, symbol, label = "flattening", "↘", "下降走平中"
    else:
        state, symbol, label = "falling", "↓", "下斜"

    return {
        "state": state,
        "symbol": symbol,
        "label": label,
        "recent_5d_slope_pct_per_day": _round(recent_slope),
        "previous_5d_slope_pct_per_day": _round(previous_slope),
        "slope_improvement_pct_per_day": _round(improvement),
        "long_friendly": state in {"rising", "flat", "flattening"},
    }


def _run_start(points: list[dict[str, Any]], end_idx: int) -> int:
    if not points or end_idx < 0:
        return 0
    color = points[end_idx].get("color")
    idx = end_idx
    while idx > 0 and points[idx-1].get("color") == color:
        idx -= 1
    return idx


def _purple_reference(points: list[dict[str, Any]]) -> dict[str, Any] | None:
    """倒數第2個紫階梯：以目前黃階前一段紫 run；若目前仍紫則用目前紫 run。"""
    if not points:
        return None
    last = len(points) - 1
    latest_color = points[last].get("color")
    if latest_color == "yellow":
        y_start = _run_start(points, last)
        p_end = y_start - 1
        if p_end < 0 or points[p_end].get("color") != "purple":
            return None
        p_start = _run_start(points, p_end)
        purple_run = points[p_start:p_end+1]
    elif latest_color == "purple":
        p_start = _run_start(points, last)
        purple_run = points[p_start:last+1]
    else:
        return None

    if not purple_run:
        return None
    ref = purple_run[-2] if len(purple_run) >= 2 else purple_run[-1]
    return {
        "date": ref.get("date"),
        "index": int(ref.get("index", 0)),
        "ha_price": _round(ref.get("close"), 10),
        "pct_vs_midline": _round(ref.get("pct"), 6),
        "reference_quality": "second_last_purple" if len(purple_run) >= 2 else "single_purple_fallback",
        "purple_run_length": len(purple_run),
    }


def _failed_reclaim_attempts(points: list[dict[str, Any]], lookback: int = 12) -> int:
    start_limit = max(0, len(points) - lookback)
    failures = 0
    i = start_limit
    while i < len(points):
        if points[i].get("color") != "yellow":
            i += 1
            continue
        y_start = i
        while i + 1 < len(points) and points[i+1].get("color") == "yellow":
            i += 1
        y_end = i
        p_end = y_start - 1
        if p_end >= 0 and points[p_end].get("color") == "purple":
            p_start = _run_start(points, p_end)
            purple_run = points[p_start:p_end+1]
            if purple_run:
                ref = purple_run[-2] if len(purple_run) >= 2 else purple_run[-1]
                max_yellow = max(_f(p.get("close")) for p in points[y_start:y_end+1])
                if max_yellow < _f(ref.get("close")):
                    # 只有之後又回紫才算一次「反彈未過紫2」。
                    if y_end + 1 < len(points) and points[y_end+1].get("color") == "purple":
                        failures += 1
        i += 1
    return failures


def build_long_opportunity(r: dict, ladder_history: list[dict] | None = None) -> dict[str, Any]:
    """做多機會星級。只評估『現在是否值得等/進多』，不評估空方進場。"""
    del ladder_history  # 保留呼叫介面，幾何判斷直接使用 20 日實價序列。
    points = _opportunity_points(r)
    if len(points) < 6:
        return {
            "stars": 1,
            "stars_text": "★☆☆☆☆",
            "opportunity_label": "資料不足",
            "setup_id": 0,
            "setup_name": "資料不足",
            "structure_state": "資料不足",
            "trigger_stage": "T0",
            "midline": {"state": "unknown", "symbol": "?", "label": "未知"},
            "reasons": ["20日幾何資料不足"],
        }

    latest = points[-1]
    latest_idx = len(points) - 1
    latest_color = latest.get("color")
    latest_pct = _f(latest.get("pct"))
    latest_pos = _f(latest.get("band_pos"), 0.5)
    midline = _midline_regime(points)
    mid_friendly = bool(midline.get("long_friendly"))
    near_now = abs(latest_pct) <= LONG_NEAR_MIDLINE_PCT
    below_now = latest_pct < 0

    current_start = _run_start(points, latest_idx)
    current_run = points[current_start:]
    current_run_length = len(current_run)

    # 找目前黃 run 前面的紫回踩；若目前仍紫，就把目前紫 run 視為回踩。
    if latest_color == "yellow":
        pullback_end = current_start - 1
        if pullback_end >= 0 and points[pullback_end].get("color") == "purple":
            pullback_start = _run_start(points, pullback_end)
            pullback_run = points[pullback_start:pullback_end+1]
        else:
            pullback_start = current_start
            pullback_run = []
    elif latest_color == "purple":
        pullback_start = current_start
        pullback_run = current_run
    else:
        pullback_start = current_start
        pullback_run = []

    search_before = points[:pullback_start]
    breakout_candidates = [p for p in search_before if (_f(p.get("pct")) >= LONG_BREAKOUT_PCT or _f(p.get("band_pos"), 0.5) >= 0.70)]
    had_breakout = bool(breakout_candidates)
    last_breakout = breakout_candidates[-1] if breakout_candidates else None
    bars_since_breakout = latest_idx - int(last_breakout.get("index")) if last_breakout else None
    recent_breakout = bool(had_breakout and bars_since_breakout is not None and bars_since_breakout <= 14)
    prior_peak_pct = max((_f(p.get("pct")) for p in search_before), default=-999.0)
    pullback_near = bool(pullback_run and any(abs(_f(p.get("pct"))) <= LONG_NEAR_MIDLINE_PCT for p in pullback_run))
    pullback_dipped_below = bool(pullback_run and min(_f(p.get("pct")) for p in pullback_run) < 0)

    purple2 = _purple_reference(points)
    purple2_pass_price = False
    purple2_pass_relative = False
    purple2_gap_pct = None
    purple2_gap_relative = None
    if purple2:
        ref_price = _f(purple2.get("ha_price"))
        ref_pct = _f(purple2.get("pct_vs_midline"))
        if abs(ref_price) > 1e-18:
            purple2_gap_pct = (latest.get("close") - ref_price) / abs(ref_price) * 100.0
            purple2_pass_price = purple2_gap_pct >= 0
        purple2_gap_relative = latest_pct - ref_pct
        purple2_pass_relative = purple2_gap_relative >= 0

    if latest_color == "purple":
        stage = "T0"
    elif latest_color == "yellow":
        stage = "T2" if purple2 and purple2_pass_price else "T1"
    else:
        stage = "T0"

    # T2 第一次發生在哪一天，提供新鮮度。
    trigger_idx = None
    if stage == "T2" and purple2 and latest_color == "yellow":
        y_start = _run_start(points, latest_idx)
        ref_price = _f(purple2.get("ha_price"))
        for idx in range(y_start, latest_idx + 1):
            if _f(points[idx].get("close")) >= ref_price:
                trigger_idx = idx
                break
    trigger_days_ago = latest_idx - trigger_idx if trigger_idx is not None else None
    trigger_date = points[trigger_idx].get("date") if trigger_idx is not None else None

    last6 = points[-6:]
    near_count_6 = sum(abs(_f(p.get("pct"))) <= LONG_NEAR_MIDLINE_PCT for p in last6)
    transitions_6 = sum(a.get("color") != b.get("color") for a, b in zip(last6, last6[1:]))
    midline_chop = near_count_6 >= 4 and transitions_6 >= 2

    # 前低以來第一次摸中軌：最近10日先有明顯低點，之後直到現在很少碰到均衡區。
    recent10 = points[-10:]
    local_offset = max(0, len(points) - len(recent10))
    low_local = min(range(len(recent10)), key=lambda i: _f(recent10[i].get("close")))
    low_idx = local_offset + low_local
    low_point = points[low_idx]
    after_low_before_latest = points[low_idx+1:latest_idx]
    prior_touch_count = sum(abs(_f(p.get("pct"))) <= 1.2 for p in after_low_before_latest)
    first_touch_midline = bool(
        near_now
        and (_f(low_point.get("pct")) <= -3.0 or _f(low_point.get("band_pos"), 0.5) <= 0.25)
        and prior_touch_count <= 1
    )

    widths = [_f(p.get("width")) for p in points]
    sorted_widths = sorted(widths)
    q25 = sorted_widths[max(0, int((len(sorted_widths)-1) * 0.25))]
    current_width = widths[-1]
    recent_width_change = ((widths[-1]-widths[-5])/abs(widths[-5])*100.0) if len(widths) >= 5 and abs(widths[-5]) > 1e-18 else 0.0
    squeeze = bool(
        current_width <= q25 * 1.08
        and mid_friendly
        and abs(latest_pct) <= 4.0
        and recent_width_change <= 5.0
    )

    recent_min_pos = min((_f(p.get("band_pos"), 0.5) for p in points[-10:]), default=0.5)
    recent_min_pct = min((_f(p.get("pct")) for p in points[-10:]), default=0.0)
    lower_band_spring = bool((recent_min_pos <= 0.05 or recent_min_pct <= -6.0) and stage == "T2")
    fake_break_reclaim = bool(
        recent_breakout and pullback_dipped_below and stage == "T2" and latest_pct >= 0 and mid_friendly
    )

    failed_attempts = _failed_reclaim_attempts(points, 12)

    last5 = points[-5:]
    yellow5 = sum(p.get("color") == "yellow" for p in last5)
    purple5 = sum(p.get("color") == "purple" for p in last5)
    mature_bull = bool(
        yellow5 >= 4
        and latest_pct >= 7.0
        and latest_pos >= 0.80
        and midline.get("state") == "rising"
    )
    mature_bear = bool(
        purple5 >= 4
        and latest_pct <= -5.0
        and latest_pos <= 0.22
        and midline.get("state") in {"falling", "flattening"}
    )

    setup_id = 0
    setup_name = "一般等待"
    structure = "尚無明確做多機會"
    stars = 1
    reasons: list[str] = []

    # ★ 不代表失敗，而是「目前不是好的追價/摸底位置」。
    if mature_bull:
        setup_name = "成熟多頭擴張／不追"
        structure = "成熟多頭擴張"
        stars = 1
        reasons.append("連續黃階且已高乖離，屬已發動區，不追漲")
    elif mature_bear:
        setup_name = "成熟空頭擴張／不摸底"
        structure = "成熟空頭擴張"
        stars = 1
        reasons.append("連續紫階且遠離中軌，屬已發動下跌，不追跌也不急摸底")
    elif fake_break_reclaim and near_now:
        setup_id = 9
        setup_name = "回踩中軌假跌破收復"
        structure = "第3浪候選｜假跌破後收復"
        stars = 5
        reasons.append("曾突破中軌，回踩跌破後以黃階重新收復且勝紫2")
    elif recent_breakout and pullback_near and stage == "T2" and mid_friendly and abs(latest_pct) <= 4.0:
        setup_id = 3
        setup_name = "突破中軌回踩｜黃階勝紫2"
        structure = "第3浪候選｜回踩確認"
        stars = 5
        reasons.append("曾突破中軌，回踩中軌後黃階已勝倒數第2紫")
    elif lower_band_spring and midline.get("state") in {"rising", "flat"}:
        setup_id = 11
        setup_name = "下軌假跌破回收｜黃階勝紫2"
        structure = "底部Spring｜先看中軌"
        stars = 5
        reasons.append("近期觸及/跌破下軌後回收，且中軌已平或上斜")
    elif below_now and stage == "T2" and midline.get("state") in {"rising", "flat"}:
        setup_id = 5
        setup_name = "中軌下反轉｜黃階勝紫2"
        structure = "中軌下提前反轉｜先看中軌"
        stars = 5
        reasons.append("仍在中軌下，但黃階已勝紫2且中軌沒有下壓")
    elif lower_band_spring and midline.get("state") == "flattening":
        setup_id = 11
        setup_name = "下軌回收｜中軌走平中"
        structure = "底部Spring｜等待均衡改善"
        stars = 4
        reasons.append("下軌反轉成立，但中軌仍帶輕微下降慣性")
    elif recent_breakout and pullback_near and near_now and stage == "T1" and mid_friendly:
        setup_id = 2
        setup_name = "突破中軌回踩｜已轉黃待勝紫2"
        structure = "第3浪候選｜確認中"
        stars = 4
        reasons.append("回踩位置成立，已轉黃但尚未超越倒數第2紫")
    elif squeeze:
        setup_id = 10
        setup_name = "極限壓縮待爆"
        structure = "BB壓縮｜等待方向脫離"
        stars = 4
        reasons.append("BB寬度接近20日低檔，中軌不下斜且階梯仍靠近均衡")
    elif recent_breakout and pullback_near and near_now and stage == "T0" and mid_friendly:
        setup_id = 1
        setup_name = "突破中軌回踩｜仍紫等待轉黃"
        structure = "第3浪候選｜等待轉色"
        stars = 3
        reasons.append("曾突破中軌，目前紫階回踩中軌且中軌可承接")
    elif midline_chop and stage in {"T1", "T2"} and midline.get("state") == "flat":
        setup_id = 6
        setup_name = "中軌附近糾纏｜等待明顯脫離"
        structure = "中軌壓縮磨合"
        stars = 3
        reasons.append("多日於中軌附近糾纏，中軌平緩，等待自然突破")
    elif first_touch_midline and stage in {"T1", "T2"} and midline.get("state") == "flat":
        setup_id = 7
        setup_name = "前低後首次測中軌"
        structure = "首次測均衡｜等待自然突破"
        stars = 3
        reasons.append("自近期低點反彈後首次測試平緩中軌")
    elif below_now and stage == "T2" and midline.get("state") == "falling":
        setup_id = 4
        setup_name = "中軌下反轉｜但中軌仍下斜"
        structure = "逆勢反彈｜上方仍有中軌壓力"
        stars = 2
        reasons.append("黃階雖勝紫2，但下降中軌仍是動態壓力")
    elif latest_color == "purple" and below_now and failed_attempts >= 1 and midline.get("state") in {"falling", "flat", "flattening"}:
        setup_id = 8
        setup_name = "下行延續｜反彈多次未過紫2"
        structure = "反彈未扭轉階梯"
        stars = 1
        reasons.append("曾有黃階反彈，但未能吃掉紫2後再度轉紫")
    elif first_touch_midline and mid_friendly:
        setup_id = 7
        setup_name = "前低後首次測中軌｜等待"
        structure = "首次測均衡"
        stars = 3
        reasons.append("前低後已推回中軌附近，但尚缺自然突破證據")
    elif stage == "T2" and below_now and midline.get("state") == "flattening":
        setup_name = "中軌下反轉｜中軌走平中"
        structure = "提前反轉｜等待中軌鈍化完成"
        stars = 4
        reasons.append("黃階已勝紫2，中軌下降速度正在明顯鈍化")
    elif near_now and stage == "T0" and mid_friendly:
        setup_name = "中軌附近等待轉黃"
        structure = "均衡附近等待"
        stars = 3
        reasons.append("階梯靠近中軌且中軌不下斜，等待黃階證據")
    elif near_now and stage == "T1" and mid_friendly:
        setup_name = "中軌附近已轉黃｜待勝紫2"
        structure = "均衡附近確認中"
        stars = 4
        reasons.append("已轉黃且靠近中軌，但尚未勝紫2")
    elif stage == "T2" and mid_friendly and abs(latest_pct) <= 5.0:
        setup_name = "一般黃階勝紫2"
        structure = "轉強確認"
        stars = 4
        reasons.append("黃階已勝紫2且中軌沒有明顯下壓")
    else:
        setup_name = "非理想做多位置"
        structure = "等待新的幾何機會"
        stars = 1
        reasons.append("目前不符合高報酬風險比的提前進場結構")

    # 五星只保留給「剛發生」的 T2；太久或已經拉遠就降級。
    freshness = "not_triggered"
    if trigger_days_ago is not None:
        if trigger_days_ago == 0:
            freshness = "today"
        elif trigger_days_ago == 1:
            freshness = "yesterday"
        else:
            freshness = f"{trigger_days_ago}d_ago"
        if stars == 5 and trigger_days_ago >= 2:
            stars = 4 if abs(latest_pct) <= 4.0 and latest_pos <= 0.78 else 3
            reasons.append("T2已非新鮮觸發，依距中軌/通道位置降級避免追價")

    # 已離中軌太遠的任何高星 setup 都再壓低，避免 ADA 類成熟行情混入。
    if stars >= 4 and (abs(latest_pct) >= 8.0 or latest_pos >= 0.88):
        stars = 2 if latest_pct < 0 else 1
        structure = "成熟多頭擴張" if latest_pct > 0 else structure
        setup_name = "成熟擴張／不追" if latest_pct > 0 else setup_name
        reasons.append("目前已遠離中軌/逼近上軌，機會星級降為不追區")

    star_labels = {
        5: "觸發進場區",
        4: "臨界確認區",
        3: "結構等待區",
        2: "逆勢反轉區",
        1: "非追價區",
    }
    stars_text = "★" * stars + "☆" * (5 - stars)

    if purple2:
        purple2 = dict(purple2)
        purple2.update({
            "current_gap_price_pct": _round(purple2_gap_pct, 6),
            "current_gap_relative_points": _round(purple2_gap_relative, 6),
            "passed_by_actual_ha_price": bool(purple2_pass_price),
            "passed_by_midline_relative_pct": bool(purple2_pass_relative),
        })

    return {
        "stars": int(stars),
        "stars_text": stars_text,
        "opportunity_label": star_labels[stars],
        "setup_id": int(setup_id),
        "setup_name": setup_name,
        "structure_state": structure,
        "trigger_stage": stage,
        "trigger_stage_meaning": {
            "T0": "目前仍紫，等待轉黃",
            "T1": "已轉黃，但尚未超越倒數第2紫",
            "T2": "已轉黃，且已超越倒數第2紫",
        }.get(stage, "unknown"),
        "midline": midline,
        "current": {
            "ha_color": latest_color,
            "ha_price": _round(latest.get("close"), 10),
            "ha_vs_midline_pct": _round(latest_pct),
            "ha_band_position": _round(latest_pos),
            "near_midline": bool(near_now),
            "current_color_run_length": int(current_run_length),
        },
        "prior_breakout": {
            "had_breakout_before_pullback": bool(had_breakout),
            "recent_within_14d": bool(recent_breakout),
            "bars_since_last_breakout": bars_since_breakout,
            "prior_peak_pct_vs_midline": _round(prior_peak_pct),
            "pullback_near_midline": bool(pullback_near),
            "pullback_dipped_below_midline": bool(pullback_dipped_below),
        },
        "purple2_reference": purple2,
        "trigger_freshness": {
            "status": freshness,
            "trigger_date": trigger_date,
            "days_ago": trigger_days_ago,
        },
        "geometry": {
            "midline_chop_nearby": bool(midline_chop),
            "first_touch_midline_from_recent_low": bool(first_touch_midline),
            "extreme_squeeze": bool(squeeze),
            "lower_band_spring": bool(lower_band_spring),
            "fake_break_reclaim": bool(fake_break_reclaim),
            "failed_reclaim_attempts_last12d": int(failed_attempts),
            "band_width_pct": _round(current_width),
            "band_width_20d_q25_pct": _round(q25),
            "band_width_recent5_change_pct": _round(recent_width_change),
        },
        "maturity": {
            "mature_bull_expansion": bool(mature_bull),
            "mature_bear_expansion": bool(mature_bear),
        },
        "reasons": reasons,
    }
