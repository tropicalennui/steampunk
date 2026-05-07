---
title: "Guide: Automated Test Suite"
date: 2026-05-07
tags: [user-guide, testing, quality]
story: "[[US-017: Automated Test Suite]]"
---

## Overview

SteamPunk ships with a `pytest` test suite that validates the database schema, the stage/promote pipelines for all five platforms, key API routes, and the IGDB lookup function. Tests run entirely locally — no real credentials, no network calls, no external services required.

## Prerequisites

- Python 3.11+
- All dependencies installed: `pip install -r requirements.txt`
- Run from the repository root (the directory containing `pytest.ini`)

## Step-by-Step

### Run all tests

```
python -m pytest
```

Pytest discovers tests under `tests/` automatically via `pytest.ini`. A passing run looks like:

```
31 passed in 1.3s
```

### Run a specific file

```
python -m pytest tests/test_pipeline.py
```

### Run a specific test

```
python -m pytest tests/test_pipeline.py::test_promote_xbox_skips_zero_achievement_rows
```

### Run with verbose output

```
python -m pytest -v
```

Each test name and PASSED/FAILED status is printed individually.

### Run with short failure summary

```
python -m pytest --tb=short
```

Useful when a test fails and you want a compact traceback.

## What the tests cover

| File | What it checks |
|---|---|
| `test_schema.py` | All expected tables exist; `platforms` table has 5 seeded rows; `achievements` has `gamerscore_earned`/`gamerscore_total`; `library` has `purchase_source` |
| `test_pipeline.py` | `stage_*` and `promote_*` functions for Steam, GOG, PSN, Switch, and Xbox; Xbox achievement skip (zero totals); Xbox `purchase_source = 'unknown'`; idempotency for every platform |
| `test_api.py` | `GET /library` and `GET /setup` return 200; `POST /sync` redirects to `/logs` whether or not a sync is already running; `GET /api/library/columns` returns expected JSON shape |
| `test_igdb.py` | `igdb_lookup_by_external_id` returns the correct game ID on a match, `None` on an empty response, and `None` on an HTTP error |

## How tests are isolated

- **Database**: each pipeline and schema test gets a fresh in-memory DuckDB connection with the schema applied from scratch. No test writes to `steampunk.duckdb`.
- **Secrets**: a minimal `gandalf.json` is created in a temp directory for the session. Tests never read or write the real `gandalf.json`.
- **Network**: HTTP calls in `igdb_lookup_by_external_id` are intercepted with `unittest.mock.patch`. No real IGDB requests are made.
- **Sync subprocess**: the `POST /sync` route's background task is replaced with a no-op so no `collect.py` subprocess is spawned during API tests.

## Troubleshooting

**`ModuleNotFoundError: No module named 'duckdb'` (or similar)**
Run `pip install -r requirements.txt` to install all dependencies including `pytest`.

**Tests fail with `FileNotFoundError` referencing `gandalf.json`**
Make sure you are running `pytest` from the repository root, not from inside `src/` or `tests/`.

**A pipeline test fails after a schema change**
If you add or rename a column in `schema.sql`, update the corresponding assertion in `test_schema.py` and the mock data or row-count expectations in `test_pipeline.py`.

**`test_get_library_returns_200` fails**
The API tests render real Jinja2 templates. If a template file under `templates/` is missing or has a syntax error, this test will fail — fix the template first.
