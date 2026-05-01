# Insignia Poller

Implements the email-driven control plane for the Insignia ingestion v3 managed-agent pipeline.

## Run locally (development)

```bash
cd poller
python3.12 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
pytest -v
```

## Spec

See `../docs/superpowers/specs/2026-05-01-ingestion-v3-email-poller-design.md`.
