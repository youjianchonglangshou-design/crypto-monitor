from hud_segmented_loader import install_segmented_hud

install_segmented_hud()

# 名稱保留 PATTERN_SORT_OPTIONS 以免 main.py 介面改動過大；內容已全面改為「做多機會」篩選。
PATTERN_SORT_OPTIONS = [
    "依做多機會星級排序(預設)",
    "🔥 即將上漲（★★★以上）",
    "★★★★★ 已觸發",
    "★★★★ 接近觸發",
    "★★★ 等待區",
    "★★ 逆勢反轉",
    "★ 非追價區",
    "結構：回踩中軌",
    "結構：中軌下反轉",
    "結構：中軌附近糾纏",
    "結構：首次測中軌",
    "結構：極限壓縮待爆",
    "結構：成熟擴張／不追",
    "中軌：↑ 上斜",
    "中軌：→ 平緩",
    "中軌：↘ 走平中",
    "中軌：↓ 下斜",
    "依幣種英文字母順序排序",
]
