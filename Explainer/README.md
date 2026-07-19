# Explainer Module

## Layout

- `core/`: evidence report generation, multi-agent evaluation, and score summary scripts.
- `input/`: reserved for standalone explainer inputs.
- `output/`: reserved for standalone explainer outputs.
- `config/`: reserved for explainer-specific configuration.
- `legacy/`: archived explainer material.

## Run

Generate evidence report:

```powershell
D:\Anaconda_envs\envs\RIskTagger\python.exe Explainer\core\evidence_explainer.py
```

Run multi-agent evaluation:

```powershell
D:\Anaconda_envs\envs\RIskTagger\python.exe Explainer\core\multi_agent_evaluator.py
```

Summarize scores:

```powershell
D:\Anaconda_envs\envs\RIskTagger\python.exe Explainer\core\summary_scores.py
```

Default inputs and outputs are configured through `project_config.py`.

