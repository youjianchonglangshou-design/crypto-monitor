"""靜態板塊標籤。板塊標籤不代表即時資金流。"""

SECTOR_TAGS = {
    "BTC": ["核心大幣", "價值儲藏"], "ETH": ["核心大幣", "DeFi"], "BNB": ["核心大幣", "交易所"],
    "SOL": ["L1/L2", "SOL生態"], "XRP": ["支付/老幣", "核心大幣"], "ADA": ["L1/L2", "核心大幣"],
    "TRX": ["支付/老幣", "L1/L2"], "LTC": ["支付/老幣", "價值儲藏"], "BCH": ["支付/老幣", "BTC生態"],
    "LINK": ["Oracle/Data", "DeFi"], "AVAX": ["L1/L2", "DeFi"], "DOT": ["L1/L2", "跨鏈"],
    "ATOM": ["L1/L2", "跨鏈"], "SUI": ["L1/L2", "新公鏈"], "APT": ["L1/L2", "新公鏈"],
    "NEAR": ["L1/L2", "AI"], "SEI": ["L1/L2", "交易"], "STRK": ["L1/L2", "ZK"],
    "ARB": ["L1/L2", "DeFi"], "OP": ["L1/L2", "Superchain"], "POL": ["L1/L2", "Polygon"],
    "S": ["L1/L2", "Sonic"], "TIA": ["L1/L2", "模組化"], "EGLD": ["L1/L2", "支付"],
    "ETC": ["支付/老幣", "PoW"], "HBAR": ["L1/L2", "企業鏈"], "ALGO": ["L1/L2", "支付"],
    "KAVA": ["L1/L2", "DeFi"], "INJ": ["交易所/合約", "DeFi"], "HYPE": ["交易所/合約", "L1/L2"],
    "OKB": ["交易所/合約", "平台幣"], "DYDX": ["交易所/合約", "DeFi"], "GMX": ["交易所/合約", "DeFi"],
    "AAVE": ["DeFi", "借貸"], "UNI": ["DeFi", "DEX"], "CRV": ["DeFi", "DEX"], "SUSHI": ["DeFi", "DEX"],
    "1INCH": ["DeFi", "DEX聚合"], "CAKE": ["DeFi", "DEX"], "COMP": ["DeFi", "借貸"], "YFI": ["DeFi", "收益"],
    "PENDLE": ["DeFi", "收益"], "LDO": ["DeFi", "LSD"], "RPL": ["DeFi", "LSD"], "SNX": ["DeFi", "衍生品"],
    "RUNE": ["DeFi", "跨鏈"], "RAY": ["SOL生態", "DeFi"], "JUP": ["SOL生態", "DeFi"], "JTO": ["SOL生態", "LSD"],
    "PYTH": ["Oracle/Data", "SOL生態"], "ONDO": ["RWA", "DeFi"], "ENA": ["DeFi", "穩定幣"],
    "TAO": ["AI", "DePIN"], "KAITO": ["AI", "InfoFi"], "WLD": ["AI", "身份"], "GRT": ["Oracle/Data", "AI"],
    "GLM": ["DePIN", "AI"], "ICP": ["AI", "L1/L2"], "FIL": ["DePIN", "Storage"], "FLR": ["Oracle/Data", "L1/L2"],
    "VET": ["RWA", "供應鏈"], "PAXG": ["價值儲藏", "RWA"], "STX": ["BTC生態", "L1/L2"], "ORDI": ["BTC生態", "銘文"],
    "KAS": ["PoW", "L1/L2"], "ZEC": ["隱私幣", "PoW"], "ROSE": ["隱私幣", "L1/L2"],
    "DOGE": ["Meme", "核心大幣"], "SHIB": ["Meme", "ETH生態"], "PEPE": ["Meme", "ETH生態"],
    "FLOKI": ["Meme", "多鏈"], "BOME": ["Meme", "SOL生態"], "PENGU": ["Meme", "SOL生態"],
    "TRUMP": ["Meme", "SOL生態"], "MEME": ["Meme"], "WIF": ["Meme", "SOL生態"], "BONK": ["Meme", "SOL生態"],
    "MANA": ["GameFi", "元宇宙"], "SAND": ["GameFi", "元宇宙"], "GALA": ["GameFi"], "AXS": ["GameFi"],
    "IMX": ["GameFi", "L1/L2"], "ENJ": ["GameFi"], "CHZ": ["支付/老幣", "Fan Token"],
    "LPT": ["DePIN", "影音"], "LRC": ["L1/L2", "DEX"], "RSR": ["支付/老幣", "穩定幣"],
    "ASTER": ["交易所/合約", "DeFi"], "W": ["跨鏈", "Oracle/Data"],
}


def get_sector_badge(symbol: str, max_tags: int = 2) -> str:
    tags = SECTOR_TAGS.get(str(symbol).upper(), ["未分類"])
    return " · ".join(tags[:max_tags])
