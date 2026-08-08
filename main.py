from __future__ import annotations

import html
import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from typing import Any

import plotly.graph_objects as go
import numpy as np
import pandas as pd
import requests
import streamlit as st

from get import build_snapshot_payload
from ha_threshold import compute_threshold_from_daily_data
from pattern_options import PATTERN_SORT_OPTIONS
import scoring_rules as _scoring_engine

EXPECTED_ENGINE_API_VERSION = "opportunity-geometry-v3.5-dp2-state-fib-zones"
ENGINE_API_VERSION = getattr(_scoring_engine, "ENGINE_API_VERSION", "legacy-or-missing")
OPPORTUNITY_ENGINE_VERSION = getattr(_scoring_engine, "OPPORTUNITY_ENGINE_VERSION", "ENGINE-MISMATCH")
PURPLE2_RULE_VERSION = getattr(_scoring_engine, "PURPLE2_RULE_VERSION", "P2-MISMATCH")
build_long_opportunity = getattr(_scoring_engine, "build_long_opportunity", None)
build_pattern_flags = getattr(_scoring_engine, "build_pattern_flags", None)
classify_pattern = getattr(_scoring_engine, "classify_pattern", None)
score_hint = getattr(_scoring_engine, "score_hint", None)
ENGINE_FILES_SYNCED = (
    ENGINE_API_VERSION == EXPECTED_ENGINE_API_VERSION
    and all(callable(fn) for fn in (build_long_opportunity, build_pattern_flags, classify_pattern, score_hint))
)
from sector_config import get_sector_badge
from symbols_config import SYMBOLS_CONFIG

TW_TZ = timezone(timedelta(hours=8))

st.set_page_config(
    page_title="HA Crypto Terminal",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="collapsed",
)

if not ENGINE_FILES_SYNCED:
    st.error(
        "⚠️ 引擎檔版本不同步｜UI 預期 OG v3.5，但 scoring_rules.py 是："
        f"{ENGINE_API_VERSION}。請同時覆蓋 main.py、scoring_rules.py、get.py、pattern_options.py。"
    )
    st.code(
        f"EXPECTED={EXPECTED_ENGINE_API_VERSION}\n"
        f"LOADED={ENGINE_API_VERSION}\n"
        f"DISPLAY={OPPORTUNITY_ENGINE_VERSION}\n"
        f"P2={PURPLE2_RULE_VERSION}"
    )
    st.stop()

st.markdown(
    '''
<style>
html,body,[data-testid="stAppViewContainer"]{background:#1e293b;color:#f1f5f9}
[data-testid="stHeader"]{background:rgba(30,41,59,.72)}
.block-container{padding-top:3.5rem;padding-bottom:1rem}
.cyber-title{font-size:22px;font-weight:800;color:#FFEB3B;letter-spacing:1.4px;margin-top:-14px}
.cyber-subtitle{font-size:11px;color:#94a3b8}
.stButton>button{background:transparent!important;color:#13f21a!important;border:1px solid #13f21a!important;font-weight:700!important;width:100%}
[data-testid="stDataFrame"],[data-testid="stDataEditor"]{border:1px solid rgba(148,163,184,.25);border-radius:9px}
.hud-loader{
    position:relative;
    margin:10px 0 20px;
    padding:18px;
    border:1px solid rgba(34,211,238,.30);
    border-radius:18px;
    background:
        radial-gradient(circle at 18% 18%,rgba(250,204,21,.08),transparent 28%),
        radial-gradient(circle at 82% 28%,rgba(34,211,238,.09),transparent 32%),
        linear-gradient(180deg,rgba(2,10,24,.98),rgba(2,8,18,.98));
    box-shadow:0 0 0 1px rgba(15,23,42,.90) inset,0 18px 52px rgba(0,0,0,.35);
    overflow:hidden;
    isolation:isolate;
}
.hud-loader:before{
    content:"";
    position:absolute;
    inset:0;
    pointer-events:none;
    background-image:
        linear-gradient(rgba(34,211,238,.035) 1px,transparent 1px),
        linear-gradient(90deg,rgba(34,211,238,.035) 1px,transparent 1px);
    background-size:30px 30px;
    mask-image:linear-gradient(to bottom,black,transparent 78%);
    z-index:-1;
}
.hud-topline{
    display:flex;
    align-items:center;
    justify-content:space-between;
    gap:12px;
    margin-bottom:12px;
    color:#e2e8f0;
    font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;
    font-size:13px;
    font-weight:800;
    letter-spacing:.7px;
}
.hud-topline strong{color:#fde047}
.hud-live-dot{
    display:inline-block;
    width:8px;
    height:8px;
    margin-right:7px;
    border-radius:99px;
    background:#22d3ee;
    box-shadow:0 0 12px #22d3ee;
    animation:hudPulse 1.1s ease-in-out infinite alternate;
}
.hud-main{
    display:grid;
    grid-template-columns:minmax(0,1fr) 118px;
    gap:12px;
    align-items:stretch;
}
.hud-track-shell{
    position:relative;
    min-height:74px;
    padding:11px 13px;
    border:1px solid rgba(34,211,238,.42);
    clip-path:polygon(18px 0,100% 0,calc(100% - 18px) 100%,0 100%);
    background:linear-gradient(90deg,rgba(8,25,43,.96),rgba(3,13,27,.96));
    box-shadow:0 0 24px rgba(34,211,238,.10) inset;
}
.hud-track{
    position:relative;
    height:50px;
    overflow:hidden;
    border:1px solid rgba(250,204,21,.55);
    clip-path:polygon(12px 0,100% 0,calc(100% - 12px) 100%,0 100%);
    background:
        repeating-linear-gradient(135deg,rgba(15,23,42,.72) 0 15px,rgba(2,8,23,.92) 15px 30px);
}
.hud-fill{
    position:absolute;
    inset:0 auto 0 0;
    min-width:4px;
    overflow:hidden;
    background:
        repeating-linear-gradient(135deg,rgba(255,244,89,.98) 0 16px,rgba(250,204,21,.98) 16px 29px,rgba(234,179,8,.96) 29px 32px);
    box-shadow:0 0 18px rgba(250,204,21,.85),0 0 42px rgba(250,204,21,.32);
    transition:width .28s ease;
}
.hud-fill:after{
    content:"";
    position:absolute;
    inset:-30% -70px -30% auto;
    width:100px;
    transform:skewX(-20deg);
    background:linear-gradient(90deg,transparent,rgba(255,255,255,.80),transparent);
    animation:hudSweep 1.15s linear infinite;
}
.hud-percent{
    display:flex;
    align-items:center;
    justify-content:center;
    min-height:74px;
    border:1px solid rgba(34,211,238,.48);
    clip-path:polygon(14px 0,100% 0,100% calc(100% - 14px),calc(100% - 14px) 100%,0 100%,0 14px);
    color:#fde047;
    background:linear-gradient(180deg,rgba(5,25,40,.98),rgba(2,11,23,.98));
    box-shadow:0 0 20px rgba(34,211,238,.10) inset;
    font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;
    font-size:28px;
    font-weight:900;
    letter-spacing:1px;
    text-shadow:0 0 16px rgba(250,204,21,.45);
}
.hud-scan-modules{
    margin-top:10px;
    color:#67e8f9;
    font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;
    font-size:10px;
    letter-spacing:.7px;
    text-transform:uppercase;
}
.hud-module-grid{
    display:grid;
    grid-template-columns:repeat(4,minmax(0,1fr));
    gap:10px;
    margin-top:14px;
}
.hud-module{
    min-height:84px;
    padding:12px 13px;
    border:1px solid rgba(100,116,139,.25);
    border-radius:10px;
    background:linear-gradient(180deg,rgba(4,18,32,.84),rgba(2,10,22,.92));
    box-shadow:0 9px 24px rgba(0,0,0,.18);
}
.hud-module-title{
    font-size:11px;
    font-weight:800;
    letter-spacing:.45px;
}
.hud-module-state{margin-top:5px;color:#cbd5e1;font-size:11px}
.hud-segments{display:flex;gap:4px;margin-top:12px}
.hud-segments span{
    width:16px;
    height:6px;
    border:1px solid currentColor;
    border-radius:99px;
    opacity:.25;
}
.hud-segments span.on{opacity:1;background:currentColor;box-shadow:0 0 8px currentColor}
.hud-yellow{color:#facc15}.hud-teal{color:#2dd4bf}.hud-green{color:#4ade80}.hud-cyan{color:#22d3ee}
.hud-wave-wrap{
    position:relative;
    height:150px;
    margin-top:14px;
    overflow:hidden;
    border-top:1px solid rgba(34,211,238,.18);
    border-bottom:1px solid rgba(34,211,238,.12);
    background:
        radial-gradient(ellipse at center,rgba(34,211,238,.08),transparent 66%),
        linear-gradient(180deg,rgba(2,8,18,.25),rgba(2,8,18,.72));
}
.hud-wave-wrap svg{width:130%;height:100%;margin-left:-15%;filter:drop-shadow(0 0 5px rgba(34,211,238,.35))}
.hud-wave-grid{fill:none;stroke:url(#hud-wave-gradient);stroke-width:.85}
.hud-wave-grid path:nth-child(3n){opacity:.95}
.hud-wave-grid path:nth-child(3n+1){opacity:.62}
.hud-wave-grid path:nth-child(3n+2){opacity:.38}
.hud-wave-a{animation:hudWaveDrift 4.2s ease-in-out infinite alternate}
.hud-complete .hud-live-dot{background:#4ade80;box-shadow:0 0 12px #4ade80}
@keyframes hudPulse{from{opacity:.38;transform:scale(.82)}to{opacity:1;transform:scale(1.18)}}
@keyframes hudSweep{from{transform:translateX(-520px) skewX(-20deg)}to{transform:translateX(90px) skewX(-20deg)}}
@keyframes hudWaveDrift{from{transform:translate(-14px,3px)}to{transform:translate(20px,-5px)}}
@media(max-width:900px){
    .hud-module-grid{grid-template-columns:repeat(2,minmax(0,1fr))}
}
@media(max-width:620px){
    .hud-loader{padding:12px}
    .hud-main{grid-template-columns:1fr 82px}
    .hud-percent{font-size:21px}
    .hud-topline{font-size:10px}
    .hud-module-grid{grid-template-columns:1fr 1fr;gap:7px}
    .hud-wave-wrap{height:110px}
}
@media(prefers-reduced-motion:reduce){
    .hud-live-dot,.hud-fill:after,.hud-wave-a{animation:none!important}
}
</style>
''',
    unsafe_allow_html=True,
)


def format_price(price: Any) -> str:
    try:
        value = float(price)
    except Exception:
        return "—"

    if value >= 10000:
        return f"{value:,.1f}"
    if value >= 1000:
        return f"{value:,.2f}"
    if value >= 100:
        return f"{value:.2f}"
    if value >= 10:
        return f"{value:.3f}"
    if value >= 1:
        return f"{value:.4f}"
    if value >= 0.01:
        return f"{value:.5f}"
    if value >= 0.0001:
        return f"{value:.6f}"
    return f"{value:.8f}"


def _compact_price_axis_labels(
    values: list[float] | np.ndarray,
    tick_values: list[float] | np.ndarray,
) -> list[str]:
    """Return TradingView-like compact Y-axis labels.

    Example: 0.00000281 -> 0.28e-5.  Normal-priced assets keep the
    existing decimal display.  One exponent is shared by the whole chart.
    """
    finite = np.asarray(values, dtype=float)
    finite = finite[np.isfinite(finite)]
    finite = np.abs(finite[finite != 0])

    if finite.size == 0:
        return [format_price(value) for value in tick_values]

    representative = float(np.median(finite))
    if representative >= 0.0001:
        return [format_price(value) for value in tick_values]

    exponent = int(np.floor(np.log10(representative))) + 1
    scale = 10.0 ** exponent
    labels: list[str] = []
    for value in tick_values:
        scaled = float(value) / scale
        text = f"{scaled:.2f}".rstrip("0").rstrip(".")
        if text == "-0":
            text = "0"
        labels.append(f"{text}e{exponent}")
    return labels


def calculate_heikin_ashi(klines: list[dict]) -> list[dict]:
    if not klines:
        return []

    output = []
    previous_open = None
    previous_close = None

    for index, candle in enumerate(klines):
        open_price = candle["open"]
        high_price = candle["high"]
        low_price = candle["low"]
        close_price = candle["close"]

        ha_close = (
            open_price + high_price + low_price + close_price
        ) / 4.0
        ha_open = (
            (open_price + close_price) / 2.0
            if index == 0
            else (previous_open + previous_close) / 2.0
        )

        output.append(
            {
                "time": candle["time"],
                "open": ha_open,
                "high": max(high_price, ha_open, ha_close),
                "low": min(low_price, ha_open, ha_close),
                "close": ha_close,
            }
        )
        previous_open = ha_open
        previous_close = ha_close

    return output


def get_ha_color(candle: dict) -> str:
    if candle["close"] > candle["open"]:
        return "🟢"
    if candle["close"] < candle["open"]:
        return "🔴"
    return "⚫"


def calculate_bollinger_bands(
    klines: list[dict],
    period: int = 20,
    std_multiplier: float = 2.0,
):
    if len(klines) < period:
        return None, None, None

    closes = np.asarray(
        [item["close"] for item in klines[-period:]],
        dtype=float,
    )
    basis = float(np.mean(closes))
    std = float(np.std(closes, ddof=0))
    upper = basis + std_multiplier * std
    lower = basis - std_multiplier * std
    return basis, upper, lower


def calculate_bollinger_basis(klines: list[dict], period: int = 20):
    """保留舊介面；中軌仍採普通日 K close 的 SMA。"""
    basis, _, _ = calculate_bollinger_bands(klines, period=period)
    return basis


def get_bb_signal(ha_close, basis):
    if basis is None:
        return "—"
    if ha_close > basis:
        return "✅"
    if ha_close < basis:
        return "❌"
    return "—"


# Pionex public routes share an IP rate limit.
_PIONEX_RATE_LOCK = threading.Lock()
_PIONEX_NEXT_REQUEST_AT = 0.0
_PIONEX_MIN_INTERVAL_SECONDS = 0.25
_PIONEX_429_COOLDOWN_SECONDS = 65.0


def _wait_for_pionex_request_slot() -> None:
    global _PIONEX_NEXT_REQUEST_AT

    with _PIONEX_RATE_LOCK:
        now = time.monotonic()
        if now < _PIONEX_NEXT_REQUEST_AT:
            time.sleep(_PIONEX_NEXT_REQUEST_AT - now)
            now = time.monotonic()
        _PIONEX_NEXT_REQUEST_AT = now + _PIONEX_MIN_INTERVAL_SECONDS


def _set_pionex_cooldown(seconds: float) -> None:
    global _PIONEX_NEXT_REQUEST_AT

    with _PIONEX_RATE_LOCK:
        _PIONEX_NEXT_REQUEST_AT = max(
            _PIONEX_NEXT_REQUEST_AT,
            time.monotonic() + max(0.0, seconds),
        )


@st.cache_data(ttl=120, show_spinner=False)
def fetch_klines(symbol: str, interval: str, limit: int = 150):
    url = "https://api.pionex.com/api/v1/market/klines"
    params = {
        "symbol": f"{symbol}_USDT",
        "interval": interval,
        "limit": limit,
    }

    last_error = None
    for attempt in range(1, 4):
        _wait_for_pionex_request_slot()
        try:
            response = requests.get(
                url,
                params=params,
                timeout=(5, 20),
            )

            if response.status_code == 429:
                retry_after = response.headers.get("Retry-After")
                try:
                    cooldown = max(
                        _PIONEX_429_COOLDOWN_SECONDS,
                        float(retry_after) if retry_after else 0.0,
                    )
                except (TypeError, ValueError):
                    cooldown = _PIONEX_429_COOLDOWN_SECONDS

                _set_pionex_cooldown(cooldown)
                last_error = requests.HTTPError(
                    f"429 Too Many Requests; cooldown {cooldown:.0f}s",
                    response=response,
                )
                continue

            response.raise_for_status()
            rows = response.json()["data"]["klines"]
            data = [
                {
                    "time": int(row["time"]) + 8 * 3600 * 1000,
                    "open": float(row["open"]),
                    "high": float(row["high"]),
                    "low": float(row["low"]),
                    "close": float(row["close"]),
                    "volume": float(row["volume"]),
                }
                for row in rows
            ]
            data.sort(key=lambda item: item["time"])
            return data

        except requests.RequestException as exc:
            last_error = exc
            if attempt < 3:
                time.sleep(1.5 * attempt)

    if last_error is not None:
        raise last_error
    raise RuntimeError(f"Unable to fetch {symbol} {interval} klines")


def analyze_symbol(symbol: str):
    try:
        daily_raw = fetch_klines(symbol, "1D")
        four_h_raw = fetch_klines(symbol, "4H")

        if len(daily_raw) < 25 or len(four_h_raw) < 6:
            return None, f"{symbol}: 資料不足"

        daily_ha = calculate_heikin_ashi(daily_raw)
        four_h_ha = calculate_heikin_ashi(four_h_raw)
        basis, upper_band, lower_band = calculate_bollinger_bands(
            daily_raw,
            period=20,
            std_multiplier=2.0,
        )
        price = four_h_raw[-1]["close"]

        previous_daily = get_ha_color(daily_ha[-2])
        current_daily = get_ha_color(daily_ha[-1])
        four_h_colors = [get_ha_color(item) for item in four_h_ha[-6:]]
        current_four_h = four_h_colors[-1]
        previous_four_h = four_h_colors[-2]
        previous_four_h_1 = four_h_colors[-3] if len(four_h_colors) >= 3 else "⚫"
        previous_four_h_2 = four_h_colors[-4] if len(four_h_colors) >= 4 else "⚫"
        previous_four_h_3 = four_h_colors[-5] if len(four_h_colors) >= 5 else "⚫"

        bb_pct = ((price - basis) / basis * 100.0) if basis else 0.0
        dot = "🟢" if bb_pct > 0 else "🔴" if bb_pct < 0 else "⚫"
        abs_dev = abs(bb_pct)

        last_20 = daily_ha[-20:]
        raw_last_20 = daily_raw[-20:]
        raw_closes = [item["close"] for item in daily_raw]
        percentages = []
        band_basis_series = []
        band_upper_series = []
        band_lower_series = []

        for index, candle in enumerate(last_20):
            end_index = len(raw_closes) - (len(last_20) - 1 - index)
            if end_index >= 20:
                window = np.asarray(
                    raw_closes[end_index - 20 : end_index],
                    dtype=float,
                )
                sma = float(np.mean(window))
                std = float(np.std(window, ddof=0))
                upper = sma + 2.0 * std
                lower = sma - 2.0 * std
            else:
                sma = 0.0
                upper = np.nan
                lower = np.nan

            band_basis_series.append(sma if sma > 0 else np.nan)
            band_upper_series.append(upper)
            band_lower_series.append(lower)
            percentages.append(
                (candle["close"] - sma) / sma * 100
                if sma > 0
                else 0.0
            )

        threshold = compute_threshold_from_daily_data(
            daily_raw_candle=daily_raw[-1],
            daily_ha_open=daily_ha[-1]["open"],
            ordinary_close=price,
            precision=8,
        )
        threshold_display = (
            f"{threshold['state_emoji']} "
            f"{format_price(threshold['price'])}｜"
            f"{threshold['signed_gap_pct']:+.2f}%"
            if threshold.get("price") is not None
            else "—"
        )

        result = {
            "幣種": symbol,
            "現價": format_price(price),
            "差%": f"{dot} {bb_pct:+.2f}%",
            "均K界": threshold_display,
            "BB日上軌": format_price(upper_band),
            "BB日中軌": format_price(basis),
            "BB日下軌": format_price(lower_band),
            "BB中軌": get_bb_signal(daily_ha[-1]["close"], basis),
            "1D前": previous_daily,
            "1D當": current_daily,
            "4H前'''": previous_four_h_3,
            "4H前''": previous_four_h_2,
            "4H前'": previous_four_h_1,
            "4H前": previous_four_h,
            "4H當": current_four_h,
            "距離中軌%": f"{abs_dev:.2f}%",
            "_price": price,
            "_bb1d": basis or 0.0,
            "_bb_upper_1d": upper_band or 0.0,
            "_bb_lower_1d": lower_band or 0.0,
            "_bb_pct": bb_pct,
            "_abs_dev": abs_dev,
            "_ha_pct_series": percentages,
            "_ha_curr_pct": percentages[-1],
            "_bb_basis_series": band_basis_series,
            "_bb_upper_series": band_upper_series,
            "_bb_lower_series": band_lower_series,
            "_ha_opens_last20": [item["open"] for item in last_20],
            "_ha_closes_last20": [item["close"] for item in last_20],
            "_ha_times_last20": [item["time"] for item in last_20],
            # 結構世代判斷同時保留真實日K，讓 1.236 失效規則可看見 wick/body 的真實跌破。
            "_raw_opens_last20": [item["open"] for item in raw_last_20],
            "_raw_highs_last20": [item["high"] for item in raw_last_20],
            "_raw_lows_last20": [item["low"] for item in raw_last_20],
            "_raw_closes_last20": [item["close"] for item in raw_last_20],
            "_ha4h_color_series": four_h_colors,
            "_ha_threshold": threshold,
        }
        return result, None

    except Exception as exc:
        return None, f"{symbol}: {type(exc).__name__} - {exc}"


def preview_ladder_history(record: dict[str, Any]) -> list[dict[str, Any]]:
    output = []
    for index, (percentage, open_price, close_price, timestamp) in enumerate(
        zip(
            record["_ha_pct_series"],
            record["_ha_opens_last20"],
            record["_ha_closes_last20"],
            record["_ha_times_last20"],
        )
    ):
        color = (
            "yellow"
            if close_price > open_price
            else "purple"
            if close_price < open_price
            else "flat"
        )
        output.append(
            {
                "index": index,
                "pct_vs_midline": percentage,
                "color": color,
                "date": datetime.fromtimestamp(
                    timestamp / 1000,
                    tz=timezone.utc,
                ).strftime("%m/%d"),
            }
        )
    return output


def annotate(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    output = []
    for base in items:
        record = dict(base)
        flags = build_pattern_flags(
            record,
            preview_ladder_history(record),
        )
        record["_pattern_flags"] = flags
        record["_pattern_type_hint"] = classify_pattern(flags)
        record["_machine_score_hint_0_100"] = score_hint(
            flags,
            {"abs_dev": record["_abs_dev"]},
        )
        record["_ladder_trigger_state"] = flags.get(
            "ladder_trigger_state",
            "red",
        )
        record["_ladder_trigger_label"] = flags.get(
            "ladder_trigger_label",
            "Reset",
        )
        # 新版主判斷：只評估做多「機會位置」，不把趨勢強弱等同進場價值。
        record["_long_opportunity"] = build_long_opportunity(
            record,
            preview_ladder_history(record),
        )
        opp = record["_long_opportunity"]
        mid = opp.get("midline") or {}
        p2 = opp.get("purple2_reference") or {}
        record["_long_stars"] = int(opp.get("stars", 1) or 1)
        record["做多星級"] = opp.get("stars_text", "★☆☆☆☆")
        record["做多結構"] = opp.get("setup_name", "一般等待")
        record["T階段"] = opp.get("trigger_stage", "T0")
        record["中軌狀態"] = f"{mid.get('symbol','?')} {mid.get('label','未知')}"
        p2_gap = p2.get("current_gap_price_pct")
        record["紫2差距"] = "—" if p2_gap is None else f"{float(p2_gap):+.2f}%"
        output.append(record)
    return output


def trigger_badge(record: dict[str, Any]) -> str:
    state = record.get("_ladder_trigger_state", "red")
    label = html.escape(str(record.get("_ladder_trigger_label", "Reset")))
    colors = {
        "red": "#ef4444",
        "yellow": "#facc15",
        "green": "#22c55e",
    }

    lamps = []
    for name in ("red", "yellow", "green"):
        active = state == name
        color = colors[name]
        lamps.append(
            "<span style='display:inline-block;width:9px;height:9px;"
            "border-radius:99px;"
            f"background:{color if active else 'rgba(100,116,139,.28)'};"
            f"border:1px solid {color if active else 'rgba(148,163,184,.24)'}'></span>"
        )

    border = {
        "red": "rgba(239,68,68,.65)",
        "yellow": "rgba(250,204,21,.65)",
        "green": "rgba(34,197,94,.65)",
    }.get(state, "#64748b")
    text = {
        "red": "#fecaca",
        "yellow": "#fde68a",
        "green": "#86efac",
    }.get(state, "#cbd5e1")

    return (
        "<div style='display:flex;align-items:center;gap:4px;padding:4px 7px;"
        f"border:1px solid {border};border-radius:999px;color:{text};"
        "font-size:10px;font-weight:700;white-space:nowrap'>"
        f"<span style='display:flex;gap:3px'>{''.join(lamps)}</span>{label}"
        "</div>"
    )


def threshold_badge(record: dict[str, Any]) -> str:
    threshold = record.get("_ha_threshold") or {}
    price = threshold.get("price")
    gap = threshold.get("signed_gap_pct")
    state = threshold.get("state")

    if price is None:
        return ""

    if state == "yellow":
        dot, border, text, background = (
            "🟡",
            "#facc15",
            "#fde047",
            "rgba(250,204,21,.10)",
        )
    elif state == "purple":
        dot, border, text, background = (
            "🟣",
            "#8b5cf6",
            "#c4b5fd",
            "rgba(139,92,246,.10)",
        )
    else:
        dot, border, text, background = (
            "⚫",
            "#94a3b8",
            "#cbd5e1",
            "rgba(148,163,184,.10)",
        )

    meaning = html.escape(str(threshold.get("meaning", "")), quote=True)
    return (
        f"<div title='{meaning}' style='padding:4px 8px;"
        f"border:1px solid {border};border-radius:999px;"
        f"background:{background};color:{text};font-size:10px;"
        f"font-weight:700;white-space:nowrap'>{dot} 均K界 "
        f"{format_price(price)}｜{gap:+.2f}%</div>"
    )


def filter_and_sort(
    items: list[dict[str, Any]],
    option: str,
) -> list[dict[str, Any]]:
    filtered = list(items)

    if option == "🔥 即將上漲（★★★以上）":
        filtered = [x for x in filtered if int((x.get("_long_opportunity") or {}).get("stars", 1)) >= 3]
    elif option.startswith("★★★★★"):
        filtered = [x for x in filtered if int((x.get("_long_opportunity") or {}).get("stars", 1)) == 5]
    elif option.startswith("★★★★"):
        filtered = [x for x in filtered if int((x.get("_long_opportunity") or {}).get("stars", 1)) == 4]
    elif option.startswith("★★★"):
        filtered = [x for x in filtered if int((x.get("_long_opportunity") or {}).get("stars", 1)) == 3]
    elif option.startswith("★★ "):
        filtered = [x for x in filtered if int((x.get("_long_opportunity") or {}).get("stars", 1)) == 2]
    elif option.startswith("★ "):
        filtered = [x for x in filtered if int((x.get("_long_opportunity") or {}).get("stars", 1)) == 1]
    elif option.startswith("結構："):
        keyword = option.split("：", 1)[1]
        keyword_map = {
            "Wave3回踩中軌": {1, 2, 3, 9},
            "中軌下反轉": {4, 5, 11},
            "自然攻中軌": {7},
            "中軌附近糾纏": {6},
            "極限壓縮待爆": {10},
            "已離開中軌甜蜜區": {0},
            "成熟擴張／不追": set(),
        }
        if keyword == "成熟擴張／不追":
            filtered = [
                x for x in filtered
                if bool(((x.get("_long_opportunity") or {}).get("maturity") or {}).get("mature_bull_expansion"))
                or bool(((x.get("_long_opportunity") or {}).get("maturity") or {}).get("mature_bear_expansion"))
            ]
        elif keyword == "已離開中軌甜蜜區":
            filtered = [
                x for x in filtered
                if "離開中軌甜蜜區" in str((x.get("_long_opportunity") or {}).get("setup_name", ""))
                or "剩餘肉量下降" in str((x.get("_long_opportunity") or {}).get("structure_state", ""))
            ]
        else:
            ids = keyword_map.get(keyword, set())
            filtered = [x for x in filtered if int((x.get("_long_opportunity") or {}).get("setup_id", 0)) in ids]
    elif option.startswith("中軌："):
        state_map = {
            "中軌：↑ 上斜": "rising",
            "中軌：→ 平緩": "flat",
            "中軌：↘ 走平中": "flattening",
            "中軌：↓ 下斜": "falling",
        }
        wanted = state_map.get(option)
        filtered = [x for x in filtered if (((x.get("_long_opportunity") or {}).get("midline") or {}).get("state") == wanted)]

    if option == "依幣種英文字母順序排序":
        return sorted(filtered, key=lambda item: item["幣種"])

    # 星級高 → T2新鮮 → 靠近中軌 → 幣名字母。
    def sort_key(item):
        opp = item.get("_long_opportunity") or {}
        stars = int(opp.get("stars", 1))
        stage = str(opp.get("trigger_stage", "T0"))
        freshness = (opp.get("trigger_freshness") or {}).get("days_ago")
        fresh_rank = 9 if freshness is None else int(freshness)
        stage_rank = {"T2": 0, "T1": 1, "T0": 2}.get(stage, 3)
        return (-stars, stage_rank, fresh_rank, abs(float(item.get("_ha_curr_pct", 999))), item["幣種"])

    return sorted(filtered, key=sort_key)


def opportunity_badge(record: dict[str, Any]) -> str:
    opp = record.get("_long_opportunity") or {}
    stars = int(opp.get("stars", 1))
    stars_text = html.escape(str(opp.get("stars_text", "★☆☆☆☆")))
    label = html.escape(str(opp.get("opportunity_label", "非追價區")))
    palette = {
        5: ("#fde047", "rgba(250,204,21,.12)"),
        4: ("#c084fc", "rgba(192,132,252,.10)"),
        3: ("#60a5fa", "rgba(96,165,250,.10)"),
        2: ("#4ade80", "rgba(74,222,128,.09)"),
        1: ("#94a3b8", "rgba(148,163,184,.08)"),
    }
    color, bg = palette.get(stars, palette[1])
    return (
        "<div style='padding:4px 8px;border-radius:999px;white-space:nowrap;"
        f"border:1px solid {color};background:{bg};color:{color};"
        "font-size:10px;font-weight:800'>"
        f"{stars_text} {label}</div>"
    )


def geometry_badges(record: dict[str, Any]) -> str:
    opp = record.get("_long_opportunity") or {}
    mid = opp.get("midline") or {}
    stage = html.escape(str(opp.get("trigger_stage", "T0")))
    mid_text = html.escape(f"中軌 {mid.get('symbol','?')} {mid.get('label','未知')}")
    p2 = opp.get("purple2_reference") or {}
    pstruct = opp.get("purple_structure") or {}
    gap = p2.get("current_gap_price_pct")
    anchor_side = pstruct.get("anchor_side")
    if anchor_side not in {"L", "R"}:
        anchor = pstruct.get("anchor_source")
        anchor_side = "R" if anchor == "active_right_v" else "L" if anchor in {"prior_left_v", "active_left_v"} else None
    anchor_text = "右V" if anchor_side == "R" else "左V" if anchor_side == "L" else ""
    p2_text = "Purple-2 —" if gap is None else f"Purple-2{anchor_text} {float(gap):+.2f}%"
    fib = pstruct.get("fib_retracement")
    fib_text = "" if fib is None else f"｜Fib {float(fib):.3f}"
    p2_text += fib_text
    p2_color = "#fde047" if gap is not None and float(gap) >= 0 else "#c4b5fd"
    stage_color = {"T2":"#fde047", "T1":"#60a5fa", "T0":"#c4b5fd"}.get(stage, "#cbd5e1")
    return (
        "<div style='display:flex;gap:5px;flex-wrap:wrap;justify-content:flex-end'>"
        f"<span style='padding:3px 7px;border:1px solid {stage_color};border-radius:999px;color:{stage_color};font-size:10px;font-weight:800'>{stage}</span>"
        f"<span style='padding:3px 7px;border:1px solid #64748b;border-radius:999px;color:#cbd5e1;font-size:10px;font-weight:700'>{mid_text}</span>"
        f"<span style='padding:3px 7px;border:1px solid {p2_color};border-radius:999px;color:{p2_color};font-size:10px;font-weight:700'>{html.escape(p2_text)}</span>"
        "</div>"
    )

def render_hud_loader(
    slot: Any,
    symbol: str,
    completed: int,
    total: int,
    percentage: int,
    *,
    complete: bool = False,
) -> None:
    pct = max(0, min(100, int(percentage)))
    total = max(1, int(total))
    safe_symbol = html.escape(symbol or "準備中")
    status = "SCAN COMPLETE" if complete else "DEEP SCANNING"
    state_text = "完成" if complete else "處理中"

    module_defs = [
        ("MARKET DATA", "市場資料", "hud-yellow", min(100, pct * 2)),
        ("GEOMETRY ANALYSIS", "幾何分析", "hud-teal", max(0, min(100, (pct - 15) * 2))),
        ("TRIGGER MATCHING", "T0/T1/T2 比對", "hud-green", max(0, min(100, (pct - 40) * 2))),
        ("OPPORTUNITY RANK", "機會星級", "hud-cyan", max(0, min(100, (pct - 65) * 3))),
    ]
    module_cards = []
    for english, chinese, color_class, module_pct in module_defs:
        lit = 6 if complete else min(6, max(0, round(module_pct / 100 * 6)))
        segments = "".join(
            f"<span class='{'on' if index < lit else ''}'></span>"
            for index in range(6)
        )
        module_state = "完成" if complete or lit == 6 else state_text
        module_cards.append(
            f"<div class='hud-module {color_class}'>"
            f"<div class='hud-module-title'>{english}</div>"
            f"<div class='hud-module-state'>{chinese}｜{module_state}</div>"
            f"<div class='hud-segments'>{segments}</div></div>"
        )

    horizontal_paths = []
    for row in range(15):
        y = 28 + row * 7
        horizontal_paths.append(
            "<path d='M -120 {y} C 80 {a}, 220 {b}, 390 {c} "
            "S 720 {d}, 900 {e} S 1160 {f}, 1380 {g}'/>".format(
                y=y,
                a=82 + row * 2,
                b=14 + row * 3,
                c=70 + row * 2,
                d=118 - row,
                e=44 + row * 2,
                f=110 - row * 2,
                g=52 + row * 2,
            )
        )
    vertical_paths = []
    for column in range(-80, 1401, 48):
        vertical_paths.append(
            f"<path d='M {column} 158 C {column - 24} 124, "
            f"{column + 30} 68, {column} 12'/>"
        )
    wave_paths = "".join(horizontal_paths + vertical_paths)

    complete_class = " hud-complete" if complete else ""
    slot.markdown(
        f"""
        <div class="hud-loader{complete_class}">
            <div class="hud-topline">
                <div><span class="hud-live-dot"></span>{status}：<strong>{safe_symbol}</strong>｜{completed}/{total}</div>
                <div>{pct}%</div>
            </div>
            <div class="hud-main">
                <div class="hud-track-shell">
                    <div class="hud-track">
                        <div class="hud-fill" style="width:{pct}%"></div>
                    </div>
                    <div class="hud-scan-modules">SCANNING MODULES｜PRICE ACTION｜HA LADDER｜TREND STRENGTH｜VOLUME｜MOMENTUM｜SCORE CALC</div>
                </div>
                <div class="hud-percent">{pct}%</div>
            </div>
            <div class="hud-module-grid">{''.join(module_cards)}</div>
            <div class="hud-wave-wrap" aria-hidden="true">
                <svg viewBox="0 0 1300 170" preserveAspectRatio="none">
                    <defs>
                        <linearGradient id="hud-wave-gradient" x1="0" y1="0" x2="1" y2="0">
                            <stop offset="0%" stop-color="#facc15" stop-opacity=".72"/>
                            <stop offset="34%" stop-color="#22d3ee" stop-opacity=".88"/>
                            <stop offset="72%" stop-color="#2dd4bf" stop-opacity=".72"/>
                            <stop offset="100%" stop-color="#22d3ee" stop-opacity=".18"/>
                        </linearGradient>
                    </defs>
                    <g class="hud-wave-grid hud-wave-a">{wave_paths}</g>
                </svg>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

# Header
column_1, column_2, column_3, column_4 = st.columns([0.48, 0.22, 0.14, 0.16])

with column_1:
    st.markdown(
        "<div class='cyber-title' style='display:flex;align-items:center;gap:10px;flex-wrap:wrap'>"
        "Heikin-Ashi Ladder Pattern Scoring Engine"
        f"<span style='font-size:10px;line-height:1;padding:5px 8px;border:1px solid #22d3ee;"
        f"border-radius:999px;color:#67e8f9;background:rgba(34,211,238,.08);letter-spacing:.5px'>"
        f"{html.escape(OPPORTUNITY_ENGINE_VERSION)}</span>"
        "</div>",
        unsafe_allow_html=True,
    )
    st.markdown(
        "<div class='cyber-subtitle'>"
        f"STREAMLIT CLOUD | UPDATED: {datetime.now(TW_TZ):%H:%M:%S} (TWN) | "
        f"ENGINE: {html.escape(OPPORTUNITY_ENGINE_VERSION)}"
        "</div>",
        unsafe_allow_html=True,
    )

with column_2:
    selection = st.selectbox(
        "幣種群組",
        list(SYMBOLS_CONFIG),
        label_visibility="collapsed",
    )

with column_3:
    if st.button("⚡ 重新分析"):
        st.cache_data.clear()
        st.rerun()

with column_4:
    download_slot = st.empty()

symbols = SYMBOLS_CONFIG[selection]
st.caption(
    "API 安全模式：最多 2 執行緒、約每秒 4 次請求；"
    "較慢但可避免大量 429。"
)

hud_slot = st.empty()
render_hud_loader(
    hud_slot,
    "準備中",
    0,
    len(symbols),
    0,
)
results = []
errors = []

with ThreadPoolExecutor(max_workers=min(2, len(symbols))) as pool:
    futures = {
        pool.submit(analyze_symbol, symbol): symbol
        for symbol in symbols
    }
    completed = 0

    for future in as_completed(futures):
        result, error = future.result()
        completed += 1

        if result:
            results.append(result)
        if error:
            errors.append(error)

        percentage = int(completed / len(symbols) * 100)
        render_hud_loader(
            hud_slot,
            futures[future],
            completed,
            len(symbols),
            percentage,
        )

render_hud_loader(
    hud_slot,
    "全部幣種",
    len(symbols),
    len(symbols),
    100,
    complete=True,
)
time.sleep(0.9)
hud_slot.empty()

if not results:
    st.error("沒有成功取得資料。請確認網路可連線到 Pionex API。")
    if errors:
        st.code("\n".join(errors[:20]))
    st.stop()

annotated = annotate(results)
dataframe = pd.DataFrame(annotated).sort_values(
    by=["_long_stars", "幣種"],
    ascending=[False, True],
)

with st.expander(
    "📋 即時表格 / 手動檢查（點擊展開）",
    expanded=False,
):
    show_columns = [
        "幣種",
        "做多星級",
        "做多結構",
        "T階段",
        "中軌狀態",
        "紫2差距",
        "現價",
        "差%",
        "均K界",
        "BB日上軌",
        "BB日中軌",
        "BB日下軌",
        "BB中軌",
        "1D前",
        "1D當",
        "4H前'''",
        "4H前''",
        "4H前'",
        "4H前",
        "4H當",
    ]
    st.dataframe(
        dataframe[show_columns],
        use_container_width=True,
        hide_index=True,
        height=min((len(dataframe) + 1) * 34 + 5, 560),
    )
    if errors:
        st.warning(f"API 失敗 {len(errors)} 個幣種")
        st.code("\n".join(errors))

st.markdown("---")
sort_option = st.selectbox(
    "做多機會排序 / 幾何過濾方式",
    PATTERN_SORT_OPTIONS,
    index=0,
)
plot_results = filter_and_sort(annotated, sort_option)

# AI snapshot always contains all symbols, independent from the chart filter.
snapshot = build_snapshot_payload(
    df=dataframe,
    plot_results=annotated,
    selection=selection,
    sort_option=sort_option,
    title="HA Crypto Terminal",
)
# 多行縮排格式，下載後可直接閱讀，也利於 GitHub 連接器按行擷取。
snapshot_text = json.dumps(
    snapshot,
    ensure_ascii=False,
    indent=2,
) + "\n"
download_slot.download_button(
    "📥 snapshot_ai.json",
    data=snapshot_text,
    file_name="snapshot_ai.json",
    mime="application/json",
    use_container_width=True,
)

st.markdown("### 📈 做多機會掃描｜20 日 HA 階梯 + BB 幾何")
st.caption(
    f"版本：{OPPORTUNITY_ENGINE_VERSION}｜Purple-2：{PURPLE2_RULE_VERSION}｜"
    f"目前顯示 {len(plot_results)} / {len(annotated)} 張圖；"
    f"下載的 snapshot_ai.json 仍包含完整 {len(annotated)} 個幣種。"
)

column_count = 2 if len(plot_results) > 4 else 3
chart_columns = st.columns(column_count)

for index, record in enumerate(plot_results):
    with chart_columns[index % column_count]:
        with st.container(border=True):
            opp = record.get("_long_opportunity") or {}
            setup_name = html.escape(str(opp.get("setup_name", "一般等待")))
            structure_state = html.escape(str(opp.get("structure_state", "等待")))
            sector = get_sector_badge(record["幣種"])

            title = (
                "<div style='display:flex;justify-content:space-between;"
                "align-items:flex-start;gap:10px;margin-bottom:6px'>"
                "<div style='min-width:0;flex:1'>"
                "<div style='font-size:14px;font-weight:700;"
                "white-space:nowrap;overflow:hidden;text-overflow:ellipsis'>"
                f"{html.escape(record['幣種'])}　"
                f"現價 {html.escape(record['現價'])}　|　"
                f"目前偏離 {html.escape(record['差%'])}　|　"
                f"4H前 {record['4H前']} 4H當 {record['4H當']}"
                "</div>"
                "<div style='font-size:12px;color:#cbd5e1;margin-top:3px;"
                "white-space:nowrap;overflow:hidden;text-overflow:ellipsis'>"
                f"{setup_name}　｜　{structure_state}"
                "</div></div>"
                "<div style='display:flex;flex-direction:column;"
                "align-items:flex-end;gap:5px;max-width:360px'>"
                "<div style='display:flex;gap:6px;align-items:center'>"
                + opportunity_badge(record)
                + (
                    "<div style='padding:4px 8px;"
                    "border:1px solid rgba(19,242,26,.55);"
                    "border-radius:999px;background:rgba(19,242,26,.08);"
                    "color:#13f21a;font-size:10px;font-weight:700;"
                    "white-space:nowrap'>"
                    f"{html.escape(sector)}</div>"
                )
                + "</div>"
                + geometry_badges(record)
                + threshold_badge(record)
                + "</div></div>"
            )
            st.markdown(title, unsafe_allow_html=True)

            y_values = np.asarray(
                record["_ha_closes_last20"],
                dtype=float,
            )
            ha_open_values = np.asarray(
                record["_ha_opens_last20"],
                dtype=float,
            )
            basis_values = np.asarray(
                record.get("_bb_basis_series") or [],
                dtype=float,
            )
            upper_values = np.asarray(
                record.get("_bb_upper_series") or [],
                dtype=float,
            )
            lower_values = np.asarray(
                record.get("_bb_lower_series") or [],
                dtype=float,
            )
            x_values = [
                datetime.fromtimestamp(
                    timestamp / 1000,
                    tz=timezone.utc,
                )
                for timestamp in record["_ha_times_last20"]
            ]

            figure = go.Figure()

            # ── 布林帶：普通日 K close 計算，座標為實際價格 ──
            if len(basis_values) == len(x_values):
                figure.add_trace(
                    go.Scatter(
                        x=x_values,
                        y=upper_values,
                        mode="lines",
                        line=dict(color="#b8b8b8", width=2.0),
                        opacity=0.90,
                        hoverinfo="none",
                        name="BB上軌",
                    )
                )
                figure.add_trace(
                    go.Scatter(
                        x=x_values,
                        y=lower_values,
                        mode="lines",
                        line=dict(color="#b8b8b8", width=2.0),
                        opacity=0.90,
                        fill="tonexty",
                        fillcolor="rgba(148,163,184,0.035)",
                        hoverinfo="none",
                        name="BB下軌",
                    )
                )
                figure.add_trace(
                    go.Scatter(
                        x=x_values,
                        y=basis_values,
                        mode="lines",
                        line=dict(
                            color="#8f9aa7",
                            width=1.45,
                            dash="dash",
                        ),
                        opacity=0.90,
                        hoverinfo="none",
                        name="BB中軌",
                    )
                )

            # ── 紫2參考線：做多 T1/T2 的核心門檻，讓肉眼直接核對 ──
            purple2 = (opp.get("purple2_reference") or {})
            purple2_price = purple2.get("ha_price")
            purple2_index = purple2.get("index")
            if (
                purple2_price is not None
                and purple2_index is not None
                and 0 <= int(purple2_index) < len(x_values)
            ):
                ref_idx = int(purple2_index)
                figure.add_trace(
                    go.Scatter(
                        x=[x_values[ref_idx], x_values[-1]],
                        y=[float(purple2_price), float(purple2_price)],
                        mode="lines",
                        line=dict(color="rgba(196,181,253,.65)", width=1.0, dash="dot"),
                        hoverinfo="none",
                        showlegend=False,
                    )
                )
                figure.add_annotation(
                    x=x_values[ref_idx],
                    y=float(purple2_price),
                    text=(
                        "P2-R"
                        if ((opp.get("purple_structure") or {}).get("anchor_side") == "R")
                        else "P2-L"
                    ),
                    showarrow=False,
                    xanchor="left",
                    yanchor="bottom",
                    xshift=3,
                    yshift=2,
                    font=dict(size=9, color="#c4b5fd"),
                )

            # ── HA 日線階梯：每一段依該根 HA 黃／紫著色 ──
            for line_index in range(len(y_values) - 1):
                color = (
                    "#FFEB3B"
                    if y_values[line_index] > ha_open_values[line_index]
                    else "#B39DDB"
                )
                figure.add_trace(
                    go.Scatter(
                        x=[x_values[line_index], x_values[line_index + 1]],
                        y=[y_values[line_index], y_values[line_index + 1]],
                        mode="lines",
                        line=dict(color=color, width=2.3, shape="hv"),
                        hoverinfo="none",
                        showlegend=False,
                    )
                )

            if x_values:
                latest_color = (
                    "#FFEB3B"
                    if y_values[-1] > ha_open_values[-1]
                    else "#B39DDB"
                )
                figure.add_trace(
                    go.Scatter(
                        x=[x_values[-1]],
                        y=[y_values[-1]],
                        mode="markers",
                        marker=dict(
                            size=9,
                            color=latest_color,
                            line=dict(color="white", width=2.2),
                        ),
                        hoverinfo="none",
                        showlegend=False,
                    )
                )
                figure.add_annotation(
                    x=x_values[-1],
                    y=float(y_values[-1]),
                    text=f"{record['_ha_curr_pct']:+.2f}%",
                    showarrow=False,
                    xanchor="right",
                    yanchor="bottom",
                    xshift=-5,
                    yshift=3,
                    font=dict(size=10, color=latest_color),
                )

            # ── 實價 Y 軸範圍與 TradingView 類似緊湊刻度 ──
            axis_scale_values = np.concatenate([
                y_values[np.isfinite(y_values)],
                basis_values[np.isfinite(basis_values)],
                upper_values[np.isfinite(upper_values)],
                lower_values[np.isfinite(lower_values)],
            ])
            if axis_scale_values.size:
                y_min = float(np.min(axis_scale_values))
                y_max = float(np.max(axis_scale_values))
                y_span = y_max - y_min
                if y_span <= 0:
                    y_span = max(abs(y_max) * 0.08, 1e-12)
                y_pad = y_span * 0.055
                y_range = [y_min - y_pad, y_max + y_pad]
                y_ticks = np.linspace(y_range[0], y_range[1], 6)
                y_ticktext = _compact_price_axis_labels(
                    axis_scale_values,
                    y_ticks,
                )
            else:
                y_range = None
                y_ticks = None
                y_ticktext = None

            figure.update_layout(
                height=290,
                margin=dict(l=4, r=5, t=2, b=4),
                paper_bgcolor="#1e293b",
                plot_bgcolor="#1e293b",
                showlegend=False,
                hovermode="closest",
                hoverdistance=-1,
                dragmode=False,
                font=dict(color="#94a3b8"),
            )
            figure.update_xaxes(
                showgrid=True,
                gridcolor="rgba(148,163,184,0.12)",
                zeroline=False,
                showline=True,
                linecolor="#475569",
                tickfont=dict(size=9, color="#94a3b8"),
                tickformat="%m/%d",
                nticks=7,
                tickangle=-45,
                fixedrange=True,
                # TradingView 類似十字游標：垂直虛線跟著滑鼠。
                showspikes=True,
                spikecolor="rgba(226,232,240,0.78)",
                spikethickness=1,
                spikedash="dash",
                spikemode="across",
                spikesnap="cursor",
            )
            figure.update_yaxes(
                showgrid=True,
                gridcolor="rgba(148,163,184,0.12)",
                zeroline=False,
                showline=True,
                linecolor="#475569",
                tickfont=dict(size=9, color="#94a3b8"),
                tickvals=y_ticks,
                ticktext=y_ticktext,
                range=y_range,
                fixedrange=True,
                # TradingView 類似十字游標：水平虛線跟著滑鼠。
                showspikes=True,
                spikecolor="rgba(226,232,240,0.78)",
                spikethickness=1,
                spikedash="dash",
                spikemode="across",
                spikesnap="cursor",
            )

            st.plotly_chart(
                figure,
                use_container_width=True,
                config={
                    "displayModeBar": False,
                    "scrollZoom": False,
                    "responsive": True,
                },
                key=f"ha_bb_chart_{record['幣種']}_{index}",
            )
