from web3 import Web3

# 1. 填入你的 API Keys
INFURA_API_KEY = "0fa2e06a1bc74368b216f864728562da"
INFURA_URL = f"https://mainnet.infura.io/v3/{INFURA_API_KEY}"

# 添加第二个 API（例如 Alchemy，或者可以直接使用免费的公共节点）
INFURA_API_KEY2 = "5313f70ff76a4c08987aed90d4423671"
INFURA_URL2 = f"https://mainnet.infura.io/v3/{INFURA_API_KEY2}"

INFURA_API_KEY3 = "a74c9bb1a9e34c379dd086a7bddfaa40"
INFURA_URL3 = f"https://mainnet.infura.io/v3/{INFURA_API_KEY3}"

INFURA_API_KEY4 = "ae4dd50f9a3248619f59ad8d1d1723ee"
INFURA_URL4 = f"https://mainnet.infura.io/v3/{INFURA_API_KEY4}"

# 如果没有第二个 API Key，可以使用公共节点作为备用：
PUBLIC_RPC_URL = "https://ethereum-rpc.publicnode.com"


# 2. 将每个提供商包装成字典，包含实例、名称和失败计数器
providers = [
    {
        "name": "Infura Node",
        "w3": Web3(Web3.HTTPProvider(INFURA_URL)),
        "failures": 0
    },
    {
        "name": "Infura Node 1",
        "w3": Web3(Web3.HTTPProvider(INFURA_URL2)),
        "failures": 0
    },
    {
        "name": "Infura Node 2",
        "w3": Web3(Web3.HTTPProvider(INFURA_URL3)),
        "failures": 0
    },
    {
        "name": "Infura Node 3",
        "w3": Web3(Web3.HTTPProvider(INFURA_URL4)),
        "failures": 0
    },
    {
        "name": "Public Node",
        "w3": Web3(Web3.HTTPProvider(PUBLIC_RPC_URL)),
        "failures": 0
    }
]

def is_contract(address):
    # 核心逻辑：每次调用前，按失败次数(failures)升序排序。
    # 失败次数越少（如 0 次），优先级越高，排在越前面。
    providers.sort(key=lambda p: p["failures"])

    for p in providers:
        w3 = p["w3"]
        name = p["name"]

        # 检查当前节点是否连接成功
        if not w3.is_connected():
            print(f"⚠️ 节点 [{name}] 无法连接，增加失败计数...")
            p["failures"] += 1
            continue  # 跳过，尝试下一个

        try:
            # 将地址转换为 Checksum 格式
            target_address = w3.to_checksum_address(address)

            # 获取地址关联的代码
            code = w3.eth.get_code(target_address)

            # --- 请求成功 ---
            # 重置该节点的失败计数（恢复其最高优先级）
            p["failures"] = 0

            # 逻辑判断：如果 code 为 '0x' 或为空，则是普通账户（EOA）
            if code == b'' or code.hex() == '0x':
                return 0  # EOA 普通账户
            else:
                return 1  # Contract 智能合约

        except ValueError:
            return "地址格式无效。"
        except Exception as e:
            # 如果在请求过程中发生错误（如速率限制、超时）
            print(f"❌ 节点 [{name}] 请求出错 ({e})，降低其优先级...")
            p["failures"] += 1 # 增加失败次数，下次请求时它的排序会往后靠
            continue

    # 如果循环结束还没有 return，说明所有节点都失败了
    return "所有以太坊节点请求均失败，请检查 API Key、网络或请求频率。"

"""
# ---------------------------------------------------------
# 测试示例
# ---------------------------------------------------------
if __name__ == "__main__":
    # 示例 1：黑客地址（EOA 钱包）
    test_eoa = "0xA4B2Fd68593B6F34E51cb9eDB66E71c1B4Ab449e"
    print(f"测试 EOA 结果: {is_contract(test_eoa)}\n")

    # 示例 2：Uniswap V3 的路由合约地址
    test_contract = "0x3fC91A3afd70395Cd496C647d5a6CC9D4B2b7FAD"
    print(f"测试合约结果: {is_contract(test_contract)}")
"""