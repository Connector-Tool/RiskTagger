
# 1. 安装依赖：pip install openai （若使用其他模型，替换为对应 SDK，如 qianfan-sdk）
import time
from openai import OpenAI



# 大模型 API 配置（以 qwen 为例，其他模型需调整）
OPENAI_API_KEY = "X"  # 替换为你的 API Key
MODEL_NAME = "qwen3-max"
BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"

#把prompt中的{和}替换为{{和}}

prompt = """

**Task Description**:Please use the Chain-of-Thought (CoT) method to progressively reason and generate the document. The specific steps are as follows:

1. **Understand the Background**: First, review the key facts of the Bybit attack incident, extracting information from external reports.
2. **Analyze the Data**: Next, parse the statistical overview of the dataset, including account distribution, risk levels, trading patterns, etc.
3. **Identify Patterns**: Then, summarize the typical characteristics of money laundering accounts, such as trading patterns, fund flows, and temporal behaviors.
4. **Synthesize the Document**: Finally, organize the content into a coherent document according to the output template, explaining technical details in plain language.

**Input Data**:The following results obtained from experiments are provided in JSON format. Please generate the document based on these data.
```json
{{
    "external_report_summary": {{
        "event_name": "Bybit Cold Wallet Hack",
        "date": "2025-02-21",
        "id": 0,
        "attack_vector": [
            "Supply chain compromise via malicious JavaScript injection in Safe{{Wallet}} frontend",
            "DELEGATECALL-based contract logic hijacking"
        ],
        "affected_platform": "Bybit (via compromised Safe{{Wallet}} infrastructure)",
        "chain": [
            "Ethereum"
        ],
        "contract_address": [
            "0xbDd077f651EBe7f7b3cE16fe5F2b025BE2969516",
            "0x96221423681A6d52E184D440a8eFCEbB105C7242"
        ],
        "attacker_addresses": [
            "0x47666Fab8bd0Ac7003bce3f5C3585383F09486E2"
        ],
        "victim_addresses": [
            "0x1Db92e2EeBC8E0c075a02BeA49a2935BcD2dFCF4"
        ],
        "stolen_amount_usd": 1500000000,
        "stolen_amount_token": {{
            "ETH": 401000,
            "mETH": 8000,
            "cmETH": 15000,
            "stETH": 90000
        }},
        "laundering_methods": [
            "Cross-DEX swaps (Uniswap, ParaSwap)",
            "Cross-chain bridging via THORChain to BTC",
            "Dispersion across thousands of wallets",
            "Partial funneling through OKX Web3 and ExCH"
        ],
        "laundering_path": [
            "0x1Db92e2EeBC8E0c075a02BeA49a2935BcD2dFCF4 → 0x47666Fab8bd0Ac7003bce3f5C3585383F09486E2 → 0xA4B2Fd68593B6F34E51cB9eDB66E71c1B4Ab449e → 0xdd90071d52f20e85c89802e5dc1ec0a7b6475f92 → 9–40 child addresses (e.g., 0xf302572594a68aa8f951fae64ed3ae7da41c72be, 0xe5ae3cfcf4c375e07ecdbadbc2c15d8cd9f7ea63) → THORChain → BTC wallets (6,954 wallets averaging 1.71 BTC each)"
        ],
        "evidence_snippets": [
            "0x0fa09C3A328792253f8dee7116848723b72a6d2e identified as initial attacker address via transaction hash 0x46deef0f52e3a983b67abf4714448a41dd7ffd6d32d32da69d62081c68ad7882",
            "Malicious JS file: app-52c9031bfa03da47.js hosted on app.safe.global",
            "72% of funds laundered via THORChain to BTC",
            "361,255 ETH (~$9B) converted to BTC and distributed across 6,954 wallets",
            "Attacker’s gas funded from Binance exchange (traced backward from 0x0fa09C...)",
            "mETH Protocol recovered 15,000 cmETH by freezing withdrawals"
        ]
    }},
    "dataset_statistics": {{
            "basic_statistics": {{
                "money_laundering_suspect_accounts": 1250,
                "normal_accounts": 1000,
                "total_accounts": 2250,
                "address_mapping_table_count": 2442
            }},
            "risk_distribution": {{
                "low_risk": {{
                    "count": 741,
                    "percentage": "59.3%"
                }},
                "mid_risk": {{
                    "count": 284,
                    "percentage": "22.7%"
                }},
                "high_risk": {{
                    "count": 221,
                    "percentage": "17.7%"
                }},
                "unknown_risk": {{
                    "count": 4,
                    "percentage": "0.3%"
                }}
            }},
            "layer_distribution": {{
                "layer_0": {{"count": 5, "percentage": "0.4%"}},
                "layer_1": {{"count": 56, "percentage": "4.5%"}},
                "layer_2": {{"count": 106, "percentage": "8.5%"}},
                "layer_3": {{"count": 53, "percentage": "4.2%"}},
                "layer_4": {{"count": 64, "percentage": "5.1%"}},
                "layer_5": {{"count": 140, "percentage": "11.2%"}},
                "layer_6": {{"count": 16, "percentage": "1.3%"}},
                "layer_7": {{"count": 95, "percentage": "7.6%"}},
                "layer_8": {{"count": 213, "percentage": "17.0%"}},
                "layer_9": {{"count": 363, "percentage": "29.0%"}},
                "layer_10": {{"count": 71, "percentage": "5.7%"}},
                "layer_11": {{"count": 30, "percentage": "2.4%"}},
                "layer_12": {{"count": 13, "percentage": "1.0%"}},
                "layer_13": {{"count": 3, "percentage": "0.2%"}},
                "layer_14": {{"count": 6, "percentage": "0.5%"}},
                "layer_15": {{"count": 7, "percentage": "0.6%"}},
                "layer_16": {{"count": 5, "percentage": "0.4%"}},
                "layer_17": {{"count": 2, "percentage": "0.2%"}},
                "layer_18": {{"count": 1, "percentage": "0.1%"}},
                "layer_19": {{"count": 1, "percentage": "0.1%"}}
            }},
            "layer_risk_cross_analysis": {{
                "layer_0": {{
                    "high": {{"count": 1, "percentage": "20.0%"}},
                    "unknown": {{"count": 4, "percentage": "80.0%"}}
                }},
                "layer_1": {{
                    "high": {{"count": 34, "percentage": "60.7%"}},
                    "mid": {{"count": 16, "percentage": "28.6%"}},
                    "low": {{"count": 6, "percentage": "10.7%"}}
                }},
                "layer_2": {{
                    "high": {{"count": 12, "percentage": "11.3%"}},
                    "mid": {{"count": 38, "percentage": "35.8%"}},
                    "low": {{"count": 56, "percentage": "52.8%"}}
                }},
                "layer_3": {{
                    "high": {{"count": 11, "percentage": "20.8%"}},
                    "mid": {{"count": 13, "percentage": "24.5%"}},
                    "low": {{"count": 29, "percentage": "54.7%"}}
                }},
                "layer_4": {{
                    "high": {{"count": 18, "percentage": "28.1%"}},
                    "mid": {{"count": 11, "percentage": "17.2%"}},
                    "low": {{"count": 35, "percentage": "54.7%"}}
                }},
                "layer_5": {{
                    "high": {{"count": 35, "percentage": "25.0%"}},
                    "mid": {{"count": 34, "percentage": "24.3%"}},
                    "low": {{"count": 71, "percentage": "50.7%"}}
                }},
                "layer_6": {{
                    "high": {{"count": 3, "percentage": "18.8%"}},
                    "mid": {{"count": 3, "percentage": "18.8%"}},
                    "low": {{"count": 10, "percentage": "62.5%"}}
                }},
                "layer_7": {{
                    "high": {{"count": 7, "percentage": "7.4%"}},
                    "mid": {{"count": 24, "percentage": "25.3%"}},
                    "low": {{"count": 64, "percentage": "67.4%"}}
                }},
                "layer_8": {{
                    "high": {{"count": 22, "percentage": "10.3%"}},
                    "mid": {{"count": 43, "percentage": "20.2%"}},
                    "low": {{"count": 148, "percentage": "69.5%"}}
                }},
                "layer_9": {{
                    "high": {{"count": 42, "percentage": "11.6%"}},
                    "mid": {{"count": 80, "percentage": "22.0%"}},
                    "low": {{"count": 241, "percentage": "66.4%"}}
                }},
                "layer_10": {{
                    "high": {{"count": 15, "percentage": "21.1%"}},
                    "mid": {{"count": 8, "percentage": "11.3%"}},
                    "low": {{"count": 48, "percentage": "67.6%"}}
                }},
                "layer_11": {{
                    "high": {{"count": 3, "percentage": "10.0%"}},
                    "mid": {{"count": 9, "percentage": "30.0%"}},
                    "low": {{"count": 18, "percentage": "60.0%"}}
                }},
                "layer_12": {{
                    "high": {{"count": 7, "percentage": "53.8%"}},
                    "mid": {{"count": 2, "percentage": "15.4%"}},
                    "low": {{"count": 4, "percentage": "30.8%"}}
                }},
                "layer_13": {{
                    "high": {{"count": 1, "percentage": "33.3%"}},
                    "mid": {{"count": 1, "percentage": "33.3%"}},
                    "low": {{"count": 1, "percentage": "33.3%"}}
                }},
                "layer_14": {{
                    "high": {{"count": 4, "percentage": "66.7%"}},
                    "low": {{"count": 2, "percentage": "33.3%"}}
                }},
                "layer_15": {{
                    "high": {{"count": 3, "percentage": "42.9%"}},
                    "mid": {{"count": 2, "percentage": "28.6%"}},
                    "low": {{"count": 2, "percentage": "28.6%"}}
                }},
                "layer_16": {{
                    "high": {{"count": 3, "percentage": "60.0%"}},
                    "low": {{"count": 2, "percentage": "40.0%"}}
                }},
                "layer_17": {{
                    "low": {{"count": 2, "percentage": "100.0%"}}
                }},
                "layer_18": {{
                    "low": {{"count": 1, "percentage": "100.0%"}}
                }},
                "layer_19": {{
                    "low": {{"count": 1, "percentage": "100.0%"}}
                }}
            }},
            "transaction_pattern_analysis": {{
                "money_laundering_accounts": {{
                    "other": {{"count": 974, "percentage": "77.9%"}},
                    "round_numbers": {{"count": 131, "percentage": "10.5%"}},
                    "structured": {{"count": 71, "percentage": "5.7%"}},
                    "large_transfers": {{"count": 68, "percentage": "5.4%"}},
                    "high_frequency": {{"count": 6, "percentage": "0.5%"}}
                }},
                "normal_accounts": {{
                    "other": {{"count": 1000, "percentage": "100.0%"}}
                }}
            }},
            "fund_flow_characteristics": {{
                "money_laundering_accounts": {{
                    "aggregation": {{"count": 1179, "percentage": "94.3%"}},
                    "other": {{"count": 41, "percentage": "3.3%"}},
                    "layering": {{"count": 15, "percentage": "1.2%"}},
                    "dispersion": {{"count": 15, "percentage": "1.2%"}}
                }},
                "normal_accounts": {{
                    "other": {{"count": 596, "percentage": "59.6%"}},
                    "aggregation": {{"count": 404, "percentage": "40.4%"}}
                }}
            }},
            "temporal_behavior_patterns": {{
                "money_laundering_accounts": {{
                    "other": {{"count": 970, "percentage": "77.6%"}},
                    "unusual_timing": {{"count": 189, "percentage": "15.1%"}},
                    "burst_activity": {{"count": 90, "percentage": "7.2%"}},
                    "rapid_movement": {{"count": 1, "percentage": "0.1%"}}
                }},
                "normal_accounts": {{
                    "other": {{"count": 1000, "percentage": "100.0%"}}
                }}
            }},
            "key_findings_summary": {{
                "most_concentrated_laundering_layer": "Layer 9 (363 accounts)",
                "predominant_risk_level": "LOW (741 accounts)",
                "high_risk_account_percentage": "17.7%",
                "notes": [
                    "Money laundering activities are most concentrated in Layer 9",
                    "The majority of money laundering accounts are classified as low risk",
                    "Although the proportion of high-risk accounts is relatively low, they require close attention"
                ]
            }},
            "analysis_insights": {{
                "risk_distribution_insight": "Although the number of low-risk accounts is the largest, the combined proportion of medium and high-risk accounts exceeds 40%, requiring close attention.",
                "layer_concentration": "Layers 8 and 9 concentrate 46% of money laundering accounts and are key monitoring layers.",
                "transaction_patterns": "Money laundering accounts primarily adopt other complex patterns (77.9%), with limited recognition by traditional detection models.",
                "fund_flow_characteristics": "Fund aggregation is the main money laundering fund flow pattern (94.3%), consistent with the characteristics of the placement stage."
            }}
        }}
    }}
}}```
1. **Introduction**
   - Purpose of the document: To assist auditors in understanding the money laundering dataset related to the Bybit attack incident.
   - Brief introduction to the RiskTagger experimental method (using BlockchainSpider and LLM to build the dataset).
2. **Bybit Attack Incident Overview**
   - Based on external report information, summarize the event background: attack vectors, affected platforms, stolen amounts, money laundering methods, etc.
   - Describe key money laundering paths and the main addresses involved.
3. **Dataset Statistical Summary**
   - Present basic statistics: total account count, money laundering account count, normal account count.
   - Show risk distribution: number and proportion of high, medium, and low-risk accounts.
   - Analyze transaction layer distribution: account numbers at each layer, highlighting the characteristics of high-risk accounts.
4. **Money Laundering Risk Account Analysis**
   - Provide a detailed explanation of the characteristics of high-risk accounts, citing specific examples (e.g., from hacker_label_enriched.csv).
   - Discuss the typical behaviors of medium and low-risk accounts, explaining why they are flagged as suspicious.
5. **Typical Money Laundering Transaction Patterns**
   - Summarize common transaction patterns: large integer transfers, zero-value transactions, rapid dispersion, etc.
   - Provide evidence snippets from LLM judgments to enhance interpretability.
6. **Fund Flow Characteristics**
   - Describe fund aggregation and dispersion patterns, including cross-DEX swaps and cross-chain bridging.
   - Emphasize how fund flows obscure illicit origins.
7. **Temporal Behavior Patterns**
   - Analyze suspicious temporal patterns: non-working hour transactions, activity bursts, etc.
   - Explain why these patterns are associated with money laundering.
8. **Conclusion and Audit Recommendations**
   - Summarize the key findings of the dataset.
   - Provide recommendations for auditors: how to leverage this information to quickly identify money laundering addresses, with a focus on high-risk patterns and layers.

**Example of Thought Process (Internal LLM Reasoning, Not Shown in the Document):**
  - Step One: From an external report, it is observed that the Bybit attack involved a compromise of the supply chain, with stolen funds laundered through THORChain.
  - Step Two: Dataset statistics indicate 500 money laundering accounts, 40% of which are considered high risk, predominantly located in Layer 1 and Layer 2.
  - Step Three: High-risk accounts often exhibit large transfers and rapid dispersion, showing a pattern where funds are aggregated and then immediately split.
  - Step Four: Temporally, transactions mostly occur at night, aligning with the covert nature of money laundering activities.
  - Step Five: Therefore, the document should highlight these patterns to assist auditors in prioritizing investigations into high-risk layers and specific time windows.
"""

def call_openai_model(prompt: str, api_key: str, model_name: str, base_url: str) -> str:
    """调用 OpenAI 大模型，获取洗钱判断结果"""
    # 初始化客户端
    client = OpenAI(api_key=api_key, base_url=BASE_URL)
    try:
        # 发送请求（temperature=0.3 降低随机性，确保判断更严谨）
        response = client.chat.completions.create(
            model=model_name,
            messages=[
                {"role": "system", "content": "You are a professional financial crime investigation expert and blockchain audit consultant, skilled at transforming complex transaction data into clear, understandable analysis reports. Your task is to generate a detailed and audit-friendly explanatory document based on the provided experimental data. This will assist human auditors in quickly understanding the money laundering transaction paths and account roles involved in the Bybit attack incident."},
                {"role": "assistant", "content": "Yes, I understand. As a professional financial crime investigation expert and blockchain audit consultant, I will analyze the provided experimental data to generate a detailed and audit-friendly explanatory document. This will assist human auditors in quickly understanding the money laundering transaction paths and account roles involved in the Bybit attack incident, based on data-driven and logically rigorous analysis without subjective assumptions."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.3,
            max_tokens=8000  # 足够容纳详细分析结果
        )
        # 提取大模型回复
        return response.choices[0].message.content.strip()
    except Exception as e:
        return f"大模型调用失败：{str(e)}"
    
if __name__ == "__main__":
    response_text = call_openai_model(prompt, OPENAI_API_KEY, MODEL_NAME, BASE_URL)
    print(response_text)
    current_time = time.strftime("%Y%m%d-%H%M%S")
    save_path = f"G:/RiskTagger/Report_final_{current_time}.md"
    with open(save_path, "w", encoding="utf-8") as f:
        f.write(response_text)

