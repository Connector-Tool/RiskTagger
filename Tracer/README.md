# Tracer Module

## Layout

- `core/`: Tracer runtime entrypoint, reasoning/filtering code, and utilities.
- `input/reference_list/`: shared reference lists.
- `output/RiskTagger_Data/`: per-event tracing inputs, intermediate files, and results.
- `config/`: `settings.py`, `.env`, and dependency notes.
- `legacy/`: BlockchainSpider source, experiments, analysis tools, and archived scripts.

## Run

From the project root:

```powershell
D:\Anaconda_envs\envs\RIskTagger\python.exe Tracer\core\main.py
```

Set the event in `Tracer/config/settings.py` or with the environment variable:

```powershell
$env:RISKTAGGER_EVENT_NAME="HTX_&_Heco_Bridge"
```

Inputs:

```text
Tracer/output/RiskTagger_Data/<EVENT_NAME>/data/src_addr_token/<EVENT_NAME>_source_addr0.csv
Tracer/output/RiskTagger_Data/<EVENT_NAME>/report/<EVENT_NAME>_report.pdf.json
Tracer/input/reference_list/
```

Outputs:

```text
Tracer/output/RiskTagger_Data/<EVENT_NAME>/
```

