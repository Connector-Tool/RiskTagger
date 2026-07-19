# Extractor Module

## Layout

- `core/`: Extractor runtime code and entrypoint.
- `input/reports/`: source incident reports.
- `output/`: generated JSON results, evaluation artifacts, and logs.
- `config/`: `config.yaml` and local `.env`.
- `legacy/`: old experiments, historical scripts, and archived material.

## Run

From the project root:

```powershell
D:\Anaconda_envs\envs\RIskTagger\python.exe Extractor\core\Extractor_main.py
```

Dependencies for this module are recorded in:

```text
Extractor/config/requirements.txt
```

Set the event in `Extractor/config/config.yaml`:

```yaml
runtime:
  event_name: "Bybit"
```

Input:

```text
Extractor/input/reports/<EVENT_NAME>/<EVENT_NAME>_report.pdf
```

Output:

```text
Extractor/output/<EVENT_NAME>/<EVENT_NAME>_report.json
```
