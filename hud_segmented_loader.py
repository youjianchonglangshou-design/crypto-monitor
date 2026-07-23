from __future__ import annotations

import re
from typing import Any

import streamlit as st
from streamlit.delta_generator import DeltaGenerator

_SEGMENT_COUNT = 36
_FILL_PATTERN = re.compile(
    r'<div\s+class=["\']hud-fill["\']\s+'
    r'style=["\']width:\s*(\d+)%["\']\s*></div>'
)

_SEGMENT_CSS = r'''
/* Discrete diagonal HUD progress steps. */
.hud-track{
    display:flex!important;
    align-items:stretch;
    gap:4px;
    padding:5px 9px;
    box-sizing:border-box;
    background:linear-gradient(180deg,rgba(8,18,34,.96),rgba(2,8,23,.98))!important;
}
.hud-track .hud-fill{display:none!important}
.hud-progress-segment{
    position:relative;
    flex:1 1 0;
    min-width:5px;
    height:100%;
    transform:skewX(-17deg);
    transform-origin:center;
    border:1px solid rgba(71,85,105,.62);
    background:linear-gradient(180deg,rgba(15,23,42,.96),rgba(2,8,23,.99));
    box-shadow:inset 0 0 9px rgba(34,211,238,.045);
    opacity:.76;
    transition:background .20s ease,border-color .20s ease,box-shadow .20s ease,opacity .20s ease;
}
.hud-progress-segment.on{
    opacity:1;
    border-color:rgba(255,244,89,.96);
    background:linear-gradient(180deg,#fff875 0%,#facc15 56%,#eab308 100%);
    box-shadow:
        0 0 10px rgba(250,204,21,.72),
        0 0 22px rgba(250,204,21,.30),
        inset 0 0 8px rgba(255,255,255,.42);
}
.hud-progress-segment.on:after{
    content:"";
    position:absolute;
    inset:0;
    background:linear-gradient(105deg,transparent 16%,rgba(255,255,255,.56) 42%,transparent 68%);
    opacity:.34;
}
.hud-progress-segment.current{
    animation:hudSegmentPulse .72s ease-in-out infinite alternate;
}
.hud-complete .hud-progress-segment.current{animation:none}
@keyframes hudSegmentPulse{
    from{filter:brightness(.92);box-shadow:0 0 8px rgba(250,204,21,.52),0 0 16px rgba(250,204,21,.22)}
    to{filter:brightness(1.28);box-shadow:0 0 15px rgba(250,204,21,.92),0 0 31px rgba(250,204,21,.42)}
}
@media(max-width:620px){
    .hud-track{gap:2px;padding:5px 6px}
    .hud-progress-segment{min-width:2px;transform:skewX(-14deg)}
}
@media(prefers-reduced-motion:reduce){
    .hud-progress-segment.current{animation:none!important}
}
'''


def _inject_segment_css(body: str) -> str:
    if ".hud-loader{" not in body or "</style>" not in body:
        return body
    if ".hud-progress-segment{" in body:
        return body
    return body.replace("</style>", f"{_SEGMENT_CSS}\n</style>", 1)


def _build_segments(percentage: int) -> str:
    pct = max(0, min(100, int(percentage)))
    lit = _SEGMENT_COUNT if pct >= 100 else int(pct * _SEGMENT_COUNT / 100)
    if pct > 0 and lit == 0:
        lit = 1

    parts: list[str] = []
    for index in range(_SEGMENT_COUNT):
        classes = ["hud-progress-segment"]
        if index < lit:
            classes.append("on")
        if lit and index == lit - 1:
            classes.append("current")
        parts.append(f'<span class="{" ".join(classes)}"></span>')
    return "".join(parts)


def _replace_continuous_fill(body: str) -> str:
    def replace(match: re.Match[str]) -> str:
        return _build_segments(int(match.group(1)))

    return _FILL_PATTERN.sub(replace, body)


def _transform_markdown_body(body: Any) -> Any:
    if not isinstance(body, str):
        return body

    transformed = _inject_segment_css(body)
    if "hud-fill" in transformed and "width:" in transformed:
        transformed = _replace_continuous_fill(transformed)
    return transformed


def install_segmented_hud() -> None:
    """Patch only the HUD markdown so the main bar advances in slanted steps."""
    if getattr(st, "_segmented_hud_patch_installed", False):
        return

    original_module_markdown = st.markdown
    original_delta_markdown = DeltaGenerator.markdown

    def module_markdown(body: Any, *args: Any, **kwargs: Any) -> Any:
        return original_module_markdown(
            _transform_markdown_body(body),
            *args,
            **kwargs,
        )

    def delta_markdown(
        self: DeltaGenerator,
        body: Any,
        *args: Any,
        **kwargs: Any,
    ) -> Any:
        return original_delta_markdown(
            self,
            _transform_markdown_body(body),
            *args,
            **kwargs,
        )

    DeltaGenerator.markdown = delta_markdown
    st.markdown = module_markdown
    setattr(st, "_segmented_hud_patch_installed", True)
