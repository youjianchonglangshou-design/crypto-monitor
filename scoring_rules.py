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

# ==================== Opportunity Geometry（做多機會掃描 v3） ====================
# 星級只代表「現在還有多少做多進場價值」，不是趨勢強弱。
# v3：Purple-2 採 Active Right-V vs 20日左側結構V + Fib 0.618；不再逐段鏈式切換。

OPPORTUNITY_ENGINE_VERSION = "OG v3.0｜DP2-FIB-0.618"
PURPLE2_RULE_VERSION = "DP2-v3-active-right-vs-structural-left"

# 星級只代表「現在還有多少做多進場價值」，不是趨勢強弱。
# v2 重點：自適應中軌距離、真正中軌突破事件、Dynamic Purple-2 Anchor（V/V + Fib）。

MIDLINE_RISING_SLOPE_PCT_PER_DAY = 0.12
MIDLINE_FLAT_FLOOR_PCT_PER_DAY = -0.25
MIDLINE_FLATTENING_MAX_FALL_PCT_PER_DAY = -0.65
MIDLINE_FLATTENING_IMPROVEMENT_MIN = 0.12

# 不再固定用「距中軌 ±3%」。0.5 是中軌；以下用每顆幣自己的 BB 寬度正規化。
MIDLINE_NEAR_BANDPOS_DISTANCE = 0.18       # 約 band_pos 0.32 ~ 0.68
MIDLINE_SWEET_UPPER_BANDPOS = 0.68
MIDLINE_ALREADY_MOVED_BANDPOS = 0.85
MATURE_UPPER_BANDPOS = 0.88
MATURE_LOWER_BANDPOS = 0.14

BREAKOUT_CONFIRM_BANDPOS = 0.72
BREAKOUT_INVALIDATE_BANDPOS = 0.15
RETEST_FAKE_BREAK_BANDPOS = 0.32
FIB_RIGHT_V_RESET_MAX = 0.618


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
    opens = opens[-count:]
    closes = closes[-count:]
    pcts = pcts[-count:]
    mids = mids[-count:]
    uppers = uppers[-count:]
    lowers = lowers[-count:]
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

    # BNB 這類肉眼明顯微微上斜，不再被 +0.25%/日硬切成平緩。
    if recent_slope >= MIDLINE_RISING_SLOPE_PCT_PER_DAY:
        state, symbol, label = "rising", "↑", "上斜"
    elif recent_slope > MIDLINE_FLAT_FLOOR_PCT_PER_DAY:
        state, symbol, label = "flat", "→", "平緩"
    elif (
        recent_slope >= MIDLINE_FLATTENING_MAX_FALL_PCT_PER_DAY
        and improvement >= MIDLINE_FLATTENING_IMPROVEMENT_MIN
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


def _near_midline(point: dict[str, Any]) -> bool:
    """用 BB 幾何距離而非固定百分比判斷是否貼近中軌。"""
    return abs(_f(point.get("band_pos"), 0.5) - 0.5) <= MIDLINE_NEAR_BANDPOS_DISTANCE


def _purple_runs(points: list[dict[str, Any]]) -> list[dict[str, Any]]:
    runs: list[dict[str, Any]] = []
    i = 0
    run_id = 0
    while i < len(points):
        if points[i].get("color") != "purple":
            i += 1
            continue
        start = i
        while i + 1 < len(points) and points[i+1].get("color") == "purple":
            i += 1
        end = i
        indices = list(range(start, end + 1))
        # 同價最低點採第一個，避免平台底最後一根讓「紫2」變得過度容易。
        low_idx = min(indices, key=lambda j: (_f(points[j].get("close")), j))
        p2_idx = low_idx - 1 if low_idx > start and points[low_idx-1].get("color") == "purple" else None
        runs.append({
            "run_id": run_id,
            "start": start,
            "end": end,
            "length": end - start + 1,
            "low_idx": low_idx,
            "low_price": _f(points[low_idx].get("close")),
            "low_pct": _f(points[low_idx].get("pct")),
            "purple2_idx": p2_idx,
            "eligible_purple2": p2_idx is not None,
        })
        run_id += 1
        i += 1
    return runs


def _active_purple_run_id(points: list[dict[str, Any]], runs: list[dict[str, Any]]) -> int | None:
    if not runs:
        return None
    latest_idx = len(points) - 1
    if points[latest_idx].get("color") == "purple":
        for run in reversed(runs):
            if run["end"] == latest_idx:
                return int(run["run_id"])
    # 最新是黃：取目前黃 run 前一段紫作為右 V。
    if points[latest_idx].get("color") == "yellow":
        y_start = _run_start(points, latest_idx)
        for run in reversed(runs):
            if run["end"] < y_start:
                return int(run["run_id"])
    return int(runs[-1]["run_id"])


def _point_ref(points: list[dict[str, Any]], idx: int | None) -> dict[str, Any] | None:
    if idx is None or idx < 0 or idx >= len(points):
        return None
    p = points[idx]
    return {
        "date": p.get("date"),
        "index": int(idx),
        "ha_price": _round(p.get("close"), 10),
        "pct_vs_midline": _round(p.get("pct"), 6),
        "band_position": _round(p.get("band_pos"), 6),
    }


def _dynamic_purple_structure(points: list[dict[str, Any]]) -> dict[str, Any]:
    """Dynamic Purple-2 v3：只比較「目前右V」與「左側結構V」。

    肉眼規則機械化：
    1) 固定使用畫面同一組 20 根 HA。
    2) 目前/最新黃 run 前一段紫 run = Active Right-V。
    3) Active Right-V 之前，找「最低且本身有 Purple-2」的紫 run 當 Structural Left-V。
       （另保留全20根 structural_low 供 HL/LL 判斷。）
    4) Right-V 若沒有自己的 Purple-2（最低紫之前不是紫；常見於只有1階紫，
       或最低紫剛好是該 run 第一階），不能硬創 P2，沿用 Left-V。
    5) Right low <= Left low：新 Lower Low；若 Right 有 P2，Anchor 切 Right。
    6) Right low > Left low：用 Left low L -> 兩V之間最高黃 H -> Right low R 計算
       Fib retracement = (H-R)/(H-L)。
       - retracement <= 0.618：右V已建立明顯 Higher Low 價格層，且有自己的 P2 -> 切 Right。
       - retracement > 0.618：右V回得太深，仍視為原雙V/同底結構 -> 沿用 Left。
    7) Purple-2 永遠是「被選中V的最低紫之前那一階紫」，不是最低紫之後的紫。

    這樣同時處理：W/雙V、咖啡杯 Higher-Low、右V只有一階紫，以及 LINK 類深回撤。
    """
    runs = _purple_runs(points)
    active_id = _active_purple_run_id(points, runs)
    if not runs or active_id is None:
        return {
            "engine_rule": PURPLE2_RULE_VERSION,
            "active_purple2": None,
            "anchor_reason": "no_purple_run",
            "anchor_source": "none",
            "fib_retracement": None,
        }

    active_run = next((r for r in runs if int(r["run_id"]) == int(active_id)), runs[-1])
    active_idx = int(active_run["run_id"])
    prior_runs = [r for r in runs if int(r["run_id"]) < active_idx]

    all_purple_indices = [i for i, p in enumerate(points) if p.get("color") == "purple"]
    structural_low_idx = (
        min(all_purple_indices, key=lambda j: (_f(points[j].get("close")), j))
        if all_purple_indices else None
    )

    # 左側 P2 必須是真正可定義的：最低紫前一日也是紫。
    eligible_left_runs = [r for r in prior_runs if r.get("eligible_purple2")]
    left_run = (
        min(eligible_left_runs, key=lambda r: (_f(r.get("low_price")), int(r.get("low_idx", 0))))
        if eligible_left_runs else None
    )

    # 若沒有左側可用 V，只有目前右V：右V有P2就用右，否則無P2。
    if left_run is None:
        chosen = active_run if active_run.get("eligible_purple2") else None
        p2_idx = int(chosen["purple2_idx"]) if chosen and chosen.get("purple2_idx") is not None else None
        p2 = _point_ref(points, p2_idx)
        if p2 and chosen:
            p2.update({
                "reference_quality": "dynamic_purple2_v3",
                "purple_run_length": int(chosen.get("length", 0)),
                "anchor_run_id": int(chosen.get("run_id", -1)),
            })
        return {
            "engine_rule": PURPLE2_RULE_VERSION,
            "structural_low": _point_ref(points, structural_low_idx),
            "left_structural_v_low": None,
            "active_swing_low": _point_ref(points, int(active_run.get("low_idx", 0))),
            "anchor_low": _point_ref(points, int(active_run.get("low_idx", 0))) if chosen else None,
            "active_purple2": p2,
            "anchor_source": "active_right_v" if chosen else "none",
            "anchor_reason": "only_right_v_available" if chosen else "right_v_has_no_own_purple2",
            "active_right_run_id": active_idx,
            "active_right_purple_count": int(active_run.get("length", 0)),
            "active_right_has_own_purple2": bool(active_run.get("eligible_purple2")),
            "low_relation": "single_v_structure",
            "fib_retracement": None,
            "fib_zone": "unavailable",
            "fib_threshold": FIB_RIGHT_V_RESET_MAX,
            "bridge_yellow_days": 0,
            "bridge_high_price": None,
            "all_purple_runs": [
                {
                    "run_id": int(x["run_id"]), "start": int(x["start"]), "end": int(x["end"]),
                    "length": int(x["length"]), "low": _point_ref(points, int(x["low_idx"])),
                    "purple2": _point_ref(points, x.get("purple2_idx")),
                } for x in runs if int(x["run_id"]) <= active_idx
            ],
        }

    left_low = _f(left_run.get("low_price"))
    right_low = _f(active_run.get("low_price"))
    bridge_indices = [
        i for i in range(int(left_run["low_idx"]) + 1, int(active_run["start"]))
        if points[i].get("color") == "yellow"
    ]
    bridge_high_idx = max(bridge_indices, key=lambda i: _f(points[i].get("close"))) if bridge_indices else None
    bridge_high = _f(points[bridge_high_idx].get("close")) if bridge_high_idx is not None else None

    fib = None
    if bridge_high is not None and bridge_high > left_low + 1e-18:
        fib = (bridge_high - right_low) / (bridge_high - left_low)

    chosen = left_run
    relation = "same_basin"
    reason = "keep_left_default"

    if not active_run.get("eligible_purple2"):
        # 最重要的 fallback：右V沒有「最低紫前一階紫」，不管抬多高都不能硬造P2。
        relation = "right_v_no_own_purple2"
        reason = "right_v_has_no_own_purple2_fallback_left"
    elif right_low <= left_low:
        chosen = active_run
        relation = "lower_low"
        reason = "right_v_new_lower_low_reset_right"
    elif fib is None:
        relation = "no_valid_bridge"
        reason = "no_valid_yellow_bridge_keep_left"
    elif fib <= FIB_RIGHT_V_RESET_MAX:
        chosen = active_run
        relation = "higher_low_reset"
        reason = "right_v_higher_low_fib_le_0618_reset_right"
    else:
        relation = "same_basin_deep_retrace"
        reason = "right_v_retrace_gt_0618_keep_left"

    p2_idx = int(chosen["purple2_idx"]) if chosen.get("purple2_idx") is not None else None
    p2 = _point_ref(points, p2_idx)
    if p2:
        p2.update({
            "reference_quality": "dynamic_purple2_v3",
            "purple_run_length": int(chosen.get("length", 0)),
            "anchor_run_id": int(chosen.get("run_id", -1)),
        })

    if fib is None:
        fib_zone = "unavailable"
    elif fib < 0:
        fib_zone = "above_swing_high"
    elif fib < 0.5:
        fib_zone = "shallow_lt_0_5"
    elif fib <= 0.618:
        fib_zone = "golden_0_5_0_618"
    else:
        fib_zone = "deep_gt_0_618"

    anchor_source = "active_right_v" if int(chosen.get("run_id", -1)) == active_idx else "prior_left_v"

    return {
        "engine_rule": PURPLE2_RULE_VERSION,
        "structural_low": _point_ref(points, structural_low_idx),
        "left_structural_v_low": _point_ref(points, int(left_run.get("low_idx", 0))),
        "active_swing_low": _point_ref(points, int(active_run.get("low_idx", 0))),
        "anchor_low": _point_ref(points, int(chosen.get("low_idx", 0))),
        "active_purple2": p2,
        "anchor_source": anchor_source,
        "anchor_reason": reason,
        "active_right_run_id": active_idx,
        "active_right_purple_count": int(active_run.get("length", 0)),
        "active_right_has_own_purple2": bool(active_run.get("eligible_purple2")),
        "low_relation": relation,
        "fib_retracement": _round(fib, 6) if fib is not None else None,
        "fib_zone": fib_zone,
        "fib_threshold": FIB_RIGHT_V_RESET_MAX,
        "bridge_yellow_days": len(bridge_indices),
        "bridge_high_price": _round(bridge_high, 10) if bridge_high is not None else None,
        "bridge_high_index": bridge_high_idx,
        "left_run_id": int(left_run.get("run_id", -1)),
        "right_run_id": active_idx,
        "all_purple_runs": [
            {
                "run_id": int(x["run_id"]),
                "start": int(x["start"]),
                "end": int(x["end"]),
                "length": int(x["length"]),
                "low": _point_ref(points, int(x["low_idx"])),
                "purple2": _point_ref(points, x.get("purple2_idx")),
            }
            for x in runs if int(x["run_id"]) <= active_idx
        ],
    }

def _breakout_context(points: list[dict[str, Any]]) -> dict[str, Any]:
    """找真正的『由中軌下穿到中軌上』波段；若 20 日左緣已在上方，允許 left-censored 推定。"""
    if len(points) < 4:
        return {"confirmed": False}

    crossings: list[tuple[int, str]] = []
    # 20 日視窗可能剛好從已突破後開始；只有早段確實在上半部才允許推定。
    if _f(points[0].get("band_pos"), 0.5) >= 0.5:
        crossings.append((0, "left_censored"))
    for i in range(1, len(points)):
        prev_pos = _f(points[i-1].get("band_pos"), 0.5)
        cur_pos = _f(points[i].get("band_pos"), 0.5)
        if prev_pos < 0.5 <= cur_pos and _f(points[i].get("close")) >= _f(points[i-1].get("close")):
            crossings.append((i, "actual_cross"))

    candidates = []
    for cross_idx, cross_type in crossings:
        search_end = len(points) - 1
        peak_idx = max(range(cross_idx, search_end + 1), key=lambda i: _f(points[i].get("band_pos"), 0.5))
        peak_pos = _f(points[peak_idx].get("band_pos"), 0.5)
        confirm_threshold = 0.80 if cross_type == "left_censored" else BREAKOUT_CONFIRM_BANDPOS
        if peak_pos < confirm_threshold:
            continue
        after_peak = points[peak_idx+1:]
        min_pos = min((_f(p.get("band_pos"), 0.5) for p in after_peak), default=peak_pos)
        min_idx = None
        if after_peak:
            min_idx = peak_idx + 1 + min(range(len(after_peak)), key=lambda j: _f(after_peak[j].get("band_pos"), 0.5))
        invalidated = bool(after_peak and min_pos < BREAKOUT_INVALIDATE_BANDPOS)
        near_retest = any(_near_midline(p) for p in after_peak)
        candidates.append({
            "cross_index": cross_idx,
            "cross_type": cross_type,
            "cross_date": points[cross_idx].get("date"),
            "peak_index": peak_idx,
            "peak_date": points[peak_idx].get("date"),
            "peak_band_position": _round(peak_pos),
            "peak_pct_vs_midline": _round(points[peak_idx].get("pct")),
            "pullback_min_band_position": _round(min_pos),
            "pullback_min_index": min_idx,
            "pullback_near_midline": bool(near_retest),
            "cycle_invalidated": invalidated,
        })

    valid = [c for c in candidates if not c.get("cycle_invalidated")]
    if not valid:
        return {
            "confirmed": False,
            "cross_type": "none",
            "pullback_near_midline": False,
            "cycle_invalidated": bool(candidates),
            "candidates": candidates,
        }

    # 取最近形成的有效高點波段；避免很早以前的突破永遠綁住現在。
    chosen = max(valid, key=lambda c: (int(c.get("peak_index", -1)), int(c.get("cross_index", -1))))
    latest_pos = _f(points[-1].get("band_pos"), 0.5)
    min_pos = _f(chosen.get("pullback_min_band_position"), 0.5)
    chosen = dict(chosen)
    chosen.update({
        "confirmed": True,
        "retest_normal": bool(chosen.get("pullback_near_midline") and min_pos >= RETEST_FAKE_BREAK_BANDPOS),
        "retest_fake_break": bool(
            chosen.get("pullback_near_midline")
            and BREAKOUT_INVALIDATE_BANDPOS <= min_pos < RETEST_FAKE_BREAK_BANDPOS
            and latest_pos >= 0.5
        ),
        "bars_since_peak": len(points) - 1 - int(chosen.get("peak_index", len(points)-1)),
    })
    return chosen


def _failed_reclaim_attempts(points: list[dict[str, Any]], lookback: int = 12) -> int:
    """只作弱勢輔助：黃 run 未吃掉該紫 run 的『最低紫前一紫』，之後又轉紫。"""
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
            run_indices = list(range(p_start, p_end + 1))
            low_idx = min(run_indices, key=lambda j: _f(points[j].get("close"))) if run_indices else None
            ref_idx = low_idx - 1 if low_idx is not None and low_idx > p_start else None
            if ref_idx is not None:
                max_yellow = max(_f(points[j].get("close")) for j in range(y_start, y_end+1))
                if max_yellow < _f(points[ref_idx].get("close")) and y_end + 1 < len(points) and points[y_end+1].get("color") == "purple":
                    failures += 1
        i += 1
    return failures


def _first_midline_test(points: list[dict[str, Any]], latest: dict[str, Any], breakout: dict[str, Any]) -> bool:
    if breakout.get("confirmed"):
        return False
    if not _near_midline(latest):
        return False
    recent = points[-12:]
    offset = len(points) - len(recent)
    low_local = min(range(len(recent)), key=lambda i: _f(recent[i].get("band_pos"), 0.5))
    low_idx = offset + low_local
    low_pos = _f(points[low_idx].get("band_pos"), 0.5)
    if low_pos > 0.25:
        return False
    # 前低後尚未真正站到明顯的中軌上方，視為第一次攻均衡區的同一段過程。
    after_low_before_latest = points[low_idx+1:-1]
    already_broke = any(_f(p.get("band_pos"), 0.5) >= 0.58 for p in after_low_before_latest)
    return not already_broke


def build_long_opportunity(r: dict, ladder_history: list[dict] | None = None) -> dict[str, Any]:
    """做多機會星級 v2。只評估『現在是否值得等/進多』，不評估空方進場。"""
    del ladder_history
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
    below_now = latest_pos < 0.5
    midline = _midline_regime(points)
    mid_friendly = bool(midline.get("long_friendly"))
    near_now = _near_midline(latest)

    current_start = _run_start(points, latest_idx)
    current_run = points[current_start:]
    current_run_length = len(current_run)

    purple_structure = _dynamic_purple_structure(points)
    purple2 = purple_structure.get("active_purple2")
    purple2_pass_price = False
    purple2_pass_relative = False
    purple2_gap_pct = None
    purple2_gap_relative = None
    if purple2:
        ref_price = _f(purple2.get("ha_price"))
        ref_pct = _f(purple2.get("pct_vs_midline"))
        if abs(ref_price) > 1e-18:
            purple2_gap_pct = (_f(latest.get("close")) - ref_price) / abs(ref_price) * 100.0
            purple2_pass_price = purple2_gap_pct >= 0
        purple2_gap_relative = latest_pct - ref_pct
        purple2_pass_relative = purple2_gap_relative >= 0

    if latest_color == "purple":
        stage = "T0"
    elif latest_color == "yellow":
        stage = "T2" if purple2 and purple2_pass_price else "T1"
    else:
        stage = "T0"

    # 新鮮度從「目前有效 Purple-2」建立後第一次被黃階吃掉算起，不因一根新黃而重置。
    trigger_idx = None
    if stage == "T2" and purple2:
        ref_price = _f(purple2.get("ha_price"))
        ref_idx = int(purple2.get("index", 0))
        for idx in range(ref_idx + 1, latest_idx + 1):
            if points[idx].get("color") == "yellow" and _f(points[idx].get("close")) >= ref_price:
                trigger_idx = idx
                break
    trigger_days_ago = latest_idx - trigger_idx if trigger_idx is not None else None
    trigger_date = points[trigger_idx].get("date") if trigger_idx is not None else None

    breakout = _breakout_context(points)
    wave3_retest = bool(breakout.get("confirmed") and breakout.get("pullback_near_midline"))
    normal_retest = bool(breakout.get("retest_normal"))
    fake_break_retest = bool(breakout.get("retest_fake_break"))

    last6 = points[-6:]
    near_count_6 = sum(_near_midline(p) for p in last6)
    transitions_6 = sum(a.get("color") != b.get("color") for a, b in zip(last6, last6[1:]))
    midline_chop = bool(near_count_6 >= 4 and transitions_6 >= 2)
    first_touch_midline = _first_midline_test(points, latest, breakout)

    widths = [_f(p.get("width")) for p in points]
    sorted_widths = sorted(widths)
    q25 = sorted_widths[max(0, int((len(sorted_widths)-1) * 0.25))]
    current_width = widths[-1]
    recent_width_change = ((widths[-1]-widths[-5])/abs(widths[-5])*100.0) if len(widths) >= 5 and abs(widths[-5]) > 1e-18 else 0.0
    squeeze = bool(
        current_width <= q25 * 1.08
        and mid_friendly
        and near_now
        and recent_width_change <= 5.0
    )

    recent_min_pos = min((_f(p.get("band_pos"), 0.5) for p in points[-10:]), default=0.5)
    lower_band_spring = bool(recent_min_pos <= 0.05 and stage == "T2")
    failed_attempts = _failed_reclaim_attempts(points, 12)

    last5 = points[-5:]
    yellow5 = sum(p.get("color") == "yellow" for p in last5)
    purple5 = sum(p.get("color") == "purple" for p in last5)
    mature_bull = bool(
        yellow5 >= 4
        and latest_pos >= MATURE_UPPER_BANDPOS
        and midline.get("state") == "rising"
    )
    mature_bear = bool(
        purple5 >= 4
        and latest_pos <= MATURE_LOWER_BANDPOS
        and midline.get("state") in {"falling", "flattening"}
    )

    setup_id = 0
    setup_name = "一般等待"
    structure = "尚無明確做多機會"
    stars = 1
    reasons: list[str] = []

    # 先判「已經跑掉」與成熟單邊；★不是失敗，是不追。
    if mature_bull:
        setup_name = "成熟多頭擴張／不追"
        structure = "成熟多頭擴張"
        stars = 1
        reasons.append("黃階長時間位於布林上半高位，屬已發動行情，不追漲")
    elif mature_bear:
        setup_name = "成熟空頭擴張／不摸底"
        structure = "成熟空頭擴張"
        stars = 1
        reasons.append("紫階長時間位於布林下半低位，屬已發動下跌，不追跌也不急摸底")

    # 第一套：真正突破中軌 -> 回踩中軌；中軌向上/平緩時等待第3浪。
    elif wave3_retest and fake_break_retest and stage == "T2" and mid_friendly and near_now:
        setup_id = 9
        setup_name = "突破後回踩｜假跌破中軌再收復"
        structure = "第3浪候選｜假跌破收復"
        stars = 5
        reasons.append("前波是真實中軌突破，回踩曾略破均衡後已重新收復 Purple-2")
    elif wave3_retest and normal_retest and stage == "T2" and mid_friendly and near_now:
        setup_id = 3
        setup_name = "突破中軌回踩｜黃階勝 Purple-2"
        structure = "第3浪候選｜回踩確認"
        stars = 5
        reasons.append("前波真實突破中軌，回踩仍屬同一波且黃階已勝有效 Purple-2")
    elif wave3_retest and stage == "T1" and mid_friendly and near_now:
        setup_id = 2
        setup_name = "突破中軌回踩｜已轉黃待勝 Purple-2"
        structure = "第3浪候選｜確認中"
        stars = 4
        reasons.append("回踩中軌位置成立，已轉黃但尚未吃掉有效 Purple-2")
    elif wave3_retest and stage == "T0" and mid_friendly and near_now:
        setup_id = 1
        setup_name = "突破中軌回踩｜仍紫等待轉黃"
        structure = "第3浪候選｜等待轉色"
        stars = 3
        reasons.append("前波真實突破中軌，目前紫階回到自適應中軌甜蜜區，等待轉黃")

    # 第二套：中軌下反轉；Purple-2 以 V/V + Fib 動態決定。
    elif lower_band_spring and stage == "T2" and midline.get("state") in {"rising", "flat"}:
        setup_id = 11
        setup_name = "下軌 Spring｜黃階勝 Purple-2"
        structure = "底部反轉｜先看中軌"
        stars = 5
        reasons.append("近期觸及/跌破下軌後反轉，且有效 Purple-2 已被吃掉")
    elif below_now and stage == "T2" and midline.get("state") in {"rising", "flat"} and near_now:
        setup_id = 5
        setup_name = "中軌下反轉｜黃階勝 Purple-2"
        structure = "提前反轉｜準備攻中軌"
        stars = 5
        reasons.append("仍在中軌下方，但已勝動態 Purple-2，且中軌不下壓")
    elif below_now and stage == "T2" and midline.get("state") == "flattening" and near_now:
        setup_id = 5
        setup_name = "中軌下反轉｜中軌快速走平"
        structure = "提前反轉｜等待均衡改善"
        stars = 4
        reasons.append("黃階已勝 Purple-2，但中軌仍留少量下降慣性")
    elif below_now and stage == "T2" and midline.get("state") == "falling":
        setup_id = 4
        setup_name = "中軌下反轉｜但中軌仍下斜"
        structure = "逆勢反彈｜上方仍有動態壓力"
        stars = 2
        reasons.append("黃階雖勝 Purple-2，但中軌仍明顯向下")

    # 中軌附近磨合 / 壓縮 / 前低後第一次自然攻中軌。
    elif squeeze:
        setup_id = 10
        setup_name = "極限壓縮待爆"
        structure = "BB壓縮｜等待方向脫離"
        stars = 4
        reasons.append("BB寬度位於20日低檔，且階梯仍貼近自適應中軌區")
    elif first_touch_midline and mid_friendly:
        setup_id = 7
        setup_name = "前低後首次攻中軌"
        structure = "自然突破候選"
        stars = 3 if stage != "T2" else 4
        reasons.append("近期低點後首次回到中軌甜蜜區，尚未形成完整突破回踩")
    elif midline_chop and midline.get("state") == "flat":
        setup_id = 6
        setup_name = "中軌附近糾纏"
        structure = "均衡壓縮｜等待自然脫離"
        stars = 3 if stage == "T0" else 4 if stage == "T1" else 3
        reasons.append("多日於中軌附近反覆磨合，中軌平緩，等待真正脫離")

    # 有黃階但還在中軌下；若 Purple-2 尚未吃掉，只列等待，不硬升星。
    elif below_now and stage == "T1" and mid_friendly and near_now:
        setup_id = 5
        setup_name = "中軌下已轉黃｜待勝 Purple-2"
        structure = "提前反轉｜尚未觸發"
        stars = 3
        reasons.append("已轉黃但尚未勝動態 Purple-2，先不視為正式反轉")

    # 已經離開中軌甜蜜區：就算 T2 成立也降低星級，BNB 類不再五星。
    elif stage == "T2" and mid_friendly and latest_pos > MIDLINE_SWEET_UPPER_BANDPOS:
        setup_name = "轉強後已離開中軌甜蜜區"
        structure = "剩餘肉量下降"
        stars = 3 if latest_pos < MIDLINE_ALREADY_MOVED_BANDPOS else 1
        reasons.append("Purple-2 已被吃掉，但 HA 已走離中軌；星級依 BB 相對位置降級")
    elif stage == "T2" and mid_friendly and near_now:
        setup_name = "一般轉強確認"
        structure = "均衡附近轉強"
        stars = 4
        reasons.append("已勝 Purple-2 且中軌友善，但不屬明確 Wave-3 回踩")
    elif latest_color == "purple" and below_now and failed_attempts >= 1 and midline.get("state") in {"falling", "flat", "flattening"}:
        setup_id = 8
        setup_name = "紫階延續｜前次反彈未勝 Purple-2"
        structure = "反彈尚未扭轉"
        stars = 1
        reasons.append("先前黃色反彈未能吃掉有效 Purple-2，之後又回紫")
    else:
        setup_name = "非理想做多位置"
        structure = "等待新的幾何機會"
        stars = 1
        reasons.append("目前不符合提前進場或第3浪回踩條件")

    # Trigger 新鮮度：只對 4/5 星做降級；Purple-2 若沿用左V且早已被突破，不會被今天新黃誤判成『今日觸發』。
    freshness = "not_triggered"
    if trigger_days_ago is not None:
        if trigger_days_ago == 0:
            freshness = "today"
        elif trigger_days_ago == 1:
            freshness = "yesterday"
        else:
            freshness = f"{trigger_days_ago}d_ago"
        if stars == 5 and trigger_days_ago >= 2:
            stars = 4 if near_now else 3
            reasons.append("目前有效 Purple-2 早已被突破，非新鮮觸發，降級避免追價")
        elif stars == 4 and setup_id in {2, 3, 5, 9, 11} and trigger_days_ago >= 4:
            stars = 3
            reasons.append("Trigger 已過多日，機會新鮮度下降")

    # 最終自適應剩餘肉量上限；不用固定 +3/+8%。
    if stars >= 4 and latest_pos >= MIDLINE_ALREADY_MOVED_BANDPOS:
        stars = 1
        setup_name = "成熟擴張／不追"
        structure = "已離開中軌甜蜜區"
        reasons.append("HA 已接近/進入上軌區，剩餘肉量不足，不追漲")
    elif stars >= 4 and latest_pos > MIDLINE_SWEET_UPPER_BANDPOS:
        stars = 3
        reasons.append("HA 已離開中軌甜蜜區，雖然結構轉強但剩餘空間下降")

    star_labels = {
        5: "高機會｜新鮮觸發",
        4: "高機會｜臨界確認",
        3: "觀察｜結構等待",
        2: "逆勢｜條件較弱",
        1: "不追｜等待新結構",
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
    purple_structure = dict(purple_structure)
    purple_structure["active_purple2"] = purple2

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
            "T1": "已轉黃，但尚未超越動態 Purple-2",
            "T2": "已轉黃，且已超越動態 Purple-2",
        }.get(stage, "unknown"),
        "midline": midline,
        "current": {
            "ha_color": latest_color,
            "ha_price": _round(latest.get("close"), 10),
            "ha_vs_midline_pct": _round(latest_pct),
            "ha_band_position": _round(latest_pos),
            "near_midline": bool(near_now),
            "midline_band_distance": _round(abs(latest_pos - 0.5), 6),
            "current_color_run_length": int(current_run_length),
        },
        "prior_breakout": {
            "confirmed_midline_cross": bool(breakout.get("confirmed")),
            "cross_type": breakout.get("cross_type", "none"),
            "cross_date": breakout.get("cross_date"),
            "cross_index": breakout.get("cross_index"),
            "peak_date": breakout.get("peak_date"),
            "peak_index": breakout.get("peak_index"),
            "peak_band_position": breakout.get("peak_band_position"),
            "prior_peak_pct_vs_midline": breakout.get("peak_pct_vs_midline"),
            "pullback_near_midline": bool(breakout.get("pullback_near_midline")),
            "pullback_min_band_position": breakout.get("pullback_min_band_position"),
            "retest_normal": bool(breakout.get("retest_normal")),
            "retest_fake_break": bool(breakout.get("retest_fake_break")),
            "cycle_invalidated": bool(breakout.get("cycle_invalidated")),
            # 舊欄位別名保留，避免 UI/舊分析直接斷掉。
            "had_breakout_before_pullback": bool(breakout.get("confirmed")),
            "recent_within_14d": bool(breakout.get("confirmed")),
            "bars_since_last_breakout": breakout.get("bars_since_peak"),
            "pullback_dipped_below_midline": bool(_f(breakout.get("pullback_min_band_position"), 0.5) < 0.5) if breakout.get("confirmed") else False,
        },
        "purple2_reference": purple2,
        "purple_structure": purple_structure,
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
            "fake_break_reclaim": bool(fake_break_retest and stage == "T2"),
            "failed_reclaim_attempts_last12d": int(failed_attempts),
            "band_width_pct": _round(current_width),
            "band_width_20d_q25_pct": _round(q25),
            "band_width_recent5_change_pct": _round(recent_width_change),
            "near_midline_bandpos_range": [
                _round(0.5 - MIDLINE_NEAR_BANDPOS_DISTANCE, 3),
                _round(0.5 + MIDLINE_NEAR_BANDPOS_DISTANCE, 3),
            ],
        },
        "maturity": {
            "mature_bull_expansion": bool(mature_bull),
            "mature_bear_expansion": bool(mature_bear),
        },
        "reasons": reasons,
    }
