# TTB Label Verification

AI-powered prototype for verifying TTB alcohol beverage labels against
application data. Take-home project for the TTB compliance division.

## Status

Phase 1 — eval framework and extraction pipeline. The web app and deployment
come after pipeline accuracy is validated.

## Docs

- [Assignment brief](assigment.md)
- [Interview highlights & inconsistencies](docs/interview-highlights.md)
- [Architecture decisions](docs/architecture-decisions.md)

## Layout

```
pipeline/      # extraction + comparison library (pure Python, no HTTP/UI)
test_data/     # label images + expected-values JSON for eval
reports/       # eval output (committed)
docs/          # planning notes
```

## Setup

Requires Python 3.11+. Uses [uv](https://docs.astral.sh/uv/) for env management.

```bash
uv venv
uv pip install -e ".[dev]"
cp .env.example .env  # fill in OPENAI_API_KEY
```
