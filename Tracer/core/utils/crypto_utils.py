from decimal import Decimal, getcontext
from typing import Union

# 设置精度，防止计算溢出
getcontext().prec = 50

def wei_to_ether(value: Union[str, int, float, Decimal], decimals: int = 18) -> Decimal:
    """
    将 wei (或最小单位) 转换为 ether (或主单位)。
    处理不同精度的代币。
    """
    try:
        val_dec = Decimal(str(value))
        if val_dec == 0:
            return Decimal(0)
        
        divisor = Decimal(10) ** decimals
        return val_dec / divisor
    except Exception:
        return Decimal(0)

def format_token_amount(value: Union[str, int], decimals: int = 18) -> str:
    """
    格式化代币数量为字符串，保留6位小数，去除末尾0
    """
    amount = wei_to_ether(value, decimals)
    # 格式化：保留6位小数，千分位
    return f"{amount:,.6f}".rstrip('0').rstrip('.')

def is_contract_whitelisted(address: str, whitelist: set) -> bool:
    """检查合约地址是否在白名单中 (忽略大小写)"""
    if not address:
        return False
    return address.strip().lower() in whitelist


# ==========================================
# 【新增】：跨资产价值标准化 (ETH 本位映射)
# ==========================================

# 静态价格字典 (以 ETH 为单位 1.0)
TOKEN_PRICES_ETH = {
    "native": Decimal("1.0"),  # 原生 ETH
    "0x0000000000000000000000000000000000000000": Decimal("1.0"),  # 原生 ETH (占位符)
    "0xae7ab96520de3a18e5e111b5eaab095312d7fe84": Decimal("1.0"),  # stETH
    "0xd5f7838f5c461feff7fe49ea5ebaf7728bb0adfa": Decimal("1.0"),  # mETH
    "0xe6829d9a7ee3040e1276fa75293bde931859e8fa": Decimal("1.0"),  # cmETH
    # USDT 的 ETH 定价 = 1 / 当时 ETH 的美元价格 (这里按 2500 U/ETH 估算)
    "0xdac17f958d2ee523a2206206994597c13d831ec7": Decimal("0.0004"),
    "0x6B175474E89094C44Da98b954EedeAC495271d0F": Decimal("0.0004"), #DAI
    "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48": Decimal("0.0004"), #USDC
    # PYR的价格
    "0x9534ad65fb398E27Ac8F4251dAe1780B989D136e": Decimal("0.00011"),   #PYR
    # HTX_&_Heco_Bridge 事件中涉及的代币
    "0x0000000000085d4780B73119b644AE5ecd22b376": Decimal("0.0004"),   #TUSD
    "0x514910771AF9Ca656af840dff83E8264EcF986CA": Decimal("0.0057"),   #LINK
    "0x1f9840a85d5aF5bf1D1762F925BDADdC4201F984": Decimal("0.002"),    #UNI
    "0x95aD61b0a150d79219dCF64E1E6Cc01f0B64C4cE": Decimal("0.0000000034"),   #SHIB
    "0x0316EB71485b0Ab14103307bf65a021042c6d380": Decimal("6.32"),   #HBTC
}


def get_token_price_eth(contract_address: str) -> Decimal:
    """
    根据合约地址获取其对应的 ETH 价值权重。
    如果遇到不在白名单里的未知代币，默认返回 0（防止空气币干扰）。
    """
    addr_lower = contract_address.strip().lower()

    if addr_lower in ["", "0x"]:
        return TOKEN_PRICES_ETH.get("native", Decimal("1.0"))

    return TOKEN_PRICES_ETH.get(addr_lower, Decimal("0.0"))