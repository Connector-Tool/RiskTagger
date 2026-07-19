# RiskTagger

RiskTagger is a research prototype for extracting incident clues from Web3 security reports, tracing suspicious fund flows, and generating evidence explanations for risk-tagging results.

This repository is prepared as the public code release for the paper. It intentionally includes only the core implementation needed to understand and reproduce the main pipeline. The paper manuscript, frontend code, backend demo services, runtime outputs, raw reports, large reference datasets, legacy folders, and ablation-experiment variants are not included.

## Repository Structure

```text
RiskTagger/
  Extractor/          # Extracts structured clues from incident reports
  Tracer/             # Traces fund flows and tags risky addresses
  Explainer/          # Generates evidence reports and evaluation summaries
  project_config.py   # Shared path configuration
```

## Core Pipeline

RiskTagger is organized into three stages:

1. **Extractor** parses a security incident report and outputs structured JSON clues, including attacker addresses and relevant evidence.
2. **Tracer** starts from seed addresses, fetches transaction context, reasons about laundering risk, and expands the tracing graph.
3. **Explainer** combines Extractor and Tracer outputs into a human-readable evidence report.

The main Tracer entry point uses the standard `reasoner_langchain.py` and `filter.py` implementation. Ablation variants are excluded from this release.

## Environment

Use Python 3.10+ and install dependencies for the modules you need:

```powershell
pip install -r Extractor/config/requirements.txt
pip install -r Tracer/config/requirements.txt
```

Some modules rely on OpenAI-compatible LLM endpoints and blockchain explorer APIs. Do not hardcode credentials in source files. Configure keys through local `.env` files or environment variables.

Example environment variables:

```text
API_KEY=your_llm_api_key
OPENAI_API_KEY=your_llm_api_key
OPENAI_BASE_URL=your_openai_compatible_base_url
MODEL_NAME=your_model_name
OPENAI_API_KEY_EMB=your_embedding_api_key
OPENAI_BASE_URL_EMB=your_embedding_base_url
MODEL_NAME_EMB=your_embedding_model
SPIDER_API_KEYS=etherscan_key_1,etherscan_key_2
```

`.env` files are ignored by Git and should not be committed.

## Data Availability

Large datasets, raw incident reports, generated outputs, reference lists, crawler caches, and legacy experiment folders are not included in this repository. To reproduce experiments, place the required data under the paths defined in `project_config.py`, or adapt those paths to your local environment.

Expected local data locations include:

```text
Extractor/input/reports/
Extractor/output/
Tracer/input/reference_list/
Tracer/output/RiskTagger_Data/
```

## Running the Main Modules

Run commands from the project root.

Extractor:

```powershell
python Extractor/core/Extractor_main.py
```

Tracer:

```powershell
python Tracer/core/main.py
```

Explainer:

```powershell
python Explainer/core/evidence_explainer.py
```

Before running, configure the target event in `Extractor/config/config.yaml` and `Tracer/config/settings.py`, or use environment variables where supported.

## Security Notes

This public repository should not contain API keys, private `.env` files, uploaded user reports, generated job folders, frontend demo code, backend server code, raw datasets, or ablation-only implementations.

Before publishing new commits, run a secret scan over staged files and confirm that large data files are not staged.

## Citation

If you use this code, please cite the corresponding RiskTagger paper.

