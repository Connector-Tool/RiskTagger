# RiskTagger: LLM-based Agent for Automatic Annotation of Web3 Crypto Money Laundering Behaviors


## 📖 Overview

RiskTagger is an innovative LLM-based agent framework designed for automatic annotation of cryptocurrency money laundering behaviors in Web3 ecosystems. This system addresses the critical challenge of constructing high-quality anti-money laundering (AML) datasets by automating the extraction, tracing, and explanation of suspicious transaction patterns across multiple blockchain networks.

**Key Features:**

- 🔍 **Automated Clue Extraction**: Extracts key information from unstructured security reports
- 🔄 **Multi-chain Transaction Tracing**: Tracks fund flows across EVM-compatible blockchains
- 🧠 **LLM-powered Risk Reasoning**: Uses chain-of-thought reasoning for risk assessment
- 📊 **Auditor-friendly Reporting**: Generates comprehensive explanation documents
- 🎯 **High Accuracy**: 100% extraction accuracy, 84.1% expert consistency

## 🏗️ Architecture and Core modules

The system consists of three core modules:

### 1. Key-clue Extractor

- Processes unstructured documents (PDF reports, news articles)
- Identifies critical entities: addresses, contracts, stolen amounts
- Outputs structured JSON format for downstream processing

### 2. Laundering Tracer

- **Fetcher**: Retrieves intra-chain and cross-chain transactions using BlockchainSpider
- **Reasoner**: LLM-driven risk assessment with CoT reasoning and reflection mechanisms
- **Filter**: Manages search space and prevents combinatorial explosion

### 3. Data Explainer

- Transforms annotated results into structured datasets
- Generates auditor-friendly natural language reports
- Provides transparency and interpretability for compliance teams


## 📁 Output Files

The system generates four main output files:

### 1. `Bybit.json`

Structured summary of the security incident extracted from external reports:

```
{
  "event_name": "Bybit Cold Wallet Hack",
  "attacker_addresses": ["0x47666Fab8bd0Ac7003bce3f5C3585383F09486E2"],
  "stolen_amount_usd": 15000000000,
  "laundering_methods": ["Cross-DEX swaps", "Cross-chain bridging"]
}
```

### 2. `hacker_label_enriched.csv`

Contains laundering accounts with detailed risk assessments:

- `address`: Wallet address
- `label`: Risk level (High/Medium/Low)
- Evidence fields for transaction patterns, fund flows, etc.

### 3. `normal_label_enriched.csv`

Contains non-laundering accounts with justification:

- Similar structure to hacker labels but with "No Suspicion" classification

### 4. `address_mapping_bybit.json`

Mapping table for all encountered addresses with anonymized IDs:

```
{
  "0xd0ebd5e6cb8764768e70f05943070b0f034d6f77": {
    "mapped_id": "[Addr-1]",
    "original": "0xd0ebd5e6cb8764768e70f05943070b0f034d6f77"
  }
}
```

## 🔬 Experimental Results

### Evaluation on Bybit Hack Case

- **Information Extraction**: 100% accuracy in key entity identification
- **Risk Assessment**: 84.1% consistency with expert judgments
- **Report Coverage**: 90% coverage in explanation generation
- **Dataset Scale**: 1,246 suspected laundering accounts annotated across 20 layers

### Performance Metrics

| Metric              | Result | Description                   |
| :------------------ | :----- | :---------------------------- |
| Extraction Accuracy | 100%   | Key entity identification     |
| Expert Consistency  | 84.1%  | Risk level agreement          |
| False Positive Rate | 0.9%   | Misclassified normal accounts |
| Coverage Rate       | 90%    | Explanation completeness      |

## 🛠️ Technical Details

### Algorithm Workflow

1. **Initialization**: Extract seed addresses from security reports
2. **Iterative Expansion**:
   - Crawl transaction data for current layer
   - Apply LLM reasoning for risk classification
   - Propagate high-risk addresses to next layer
3. **Termination**: Stop when max depth reached or no new suspicious addresses found

### LLM Configuration

- **Model**: Qwen3-Max
- **Temperature**: 0.3 (for deterministic outputs)
- **Reasoning**: Chain-of-Thought with reflection mechanisms
- **Risk Dimensions**: Transaction patterns, fund flows, associated addresses, temporal signs

## 📊 Case Study: Bybit Hack Analysis

The system was validated on the Bybit Cold Wallet Hack (Feb 2025), one of the largest cryptocurrency thefts in history with $1.5B in stolen assets. RiskTagger successfully:

- Identified 1,246 suspicious accounts across 20 transaction layers
- Achieved 84.1% agreement with blockchain security experts
- Generated comprehensive audit reports detailing laundering patterns
- Revealed emerging trends in cross-chain money laundering

## 🔮 Future Work

- **Enhanced Robustness**: Multi-agent reasoning with specialized roles
- **External Reflection**: Integration with authoritative security labels
- **Cross-chain Expansion**: Support for non-EVM blockchains (Solana, Bitcoin)
- **Real-time Detection**: Adaptation for live transaction monitoring
- **Knowledge Standardization**: Gold-standard benchmarking corpus development
