"""幣種清單設定。"""

EXAM_SYMBOLS = [
    "BTC", "1INCH", "RAY", "RSR", "SUI", "KAVA", "INJ", "LTC", "SNX", "SUSHI",
    "TRX", "ASTER", "BOME", "JTO", "KAS", "NEAR", "PENGU", "SHIB", "SOL", "XLM",
    "XRP", "GMX", "RPL", "RUNE", "LINK", "ETH", "PEPE", "JUP", "PENDLE", "TAO",
    "KAITO", "BNB", "CAKE", "COMP", "ORDI", "ADA", "ALGO", "ARB", "UNI", "CRV",
    "ENA", "MANA", "OKB", "APT", "DOT", "FLOKI", "HBAR", "SEI", "STRK", "TRUMP",
    "BCH", "FIL", "LPT", "AAVE", "AVAX", "DOGE", "ENJ", "ICP", "LRC", "SAND",
    "STX", "VET", "ONDO", "YFI", "ATOM", "DYDX", "IMX", "ROSE", "CHZ", "GALA",
    "GRT", "HYPE", "MEME", "TIA", "W", "WLD", "ETC", "FLR", "GLM", "POL",
    "PYTH", "WIF", "BONK", "OP", "S", "PAXG", "AXS", "EGLD", "LDO", "ZEC",
]

CORE_SYMBOLS = ["BTC", "ETH", "SOL", "BNB", "XRP", "ADA", "DOGE", "LINK", "AVAX", "TRX", "LTC", "BCH"]
DEFI_SYMBOLS = ["AAVE", "UNI", "CRV", "SUSHI", "1INCH", "GMX", "PENDLE", "CAKE", "COMP", "YFI", "LDO", "DYDX", "RAY", "JUP"]
AI_SYMBOLS = ["TAO", "KAITO", "WLD", "GRT", "GLM", "ICP", "FET"]
MEME_SYMBOLS = ["DOGE", "SHIB", "PEPE", "FLOKI", "BOME", "PENGU", "TRUMP", "MEME", "WIF", "BONK"]

SYMBOLS_CONFIG = {
    "考試幣": EXAM_SYMBOLS,
    "核心幣": [s for s in EXAM_SYMBOLS if s in CORE_SYMBOLS],
    "DeFi": [s for s in EXAM_SYMBOLS if s in DEFI_SYMBOLS],
    "AI / Data": [s for s in EXAM_SYMBOLS if s in AI_SYMBOLS],
    "Meme": [s for s in EXAM_SYMBOLS if s in MEME_SYMBOLS],
}
