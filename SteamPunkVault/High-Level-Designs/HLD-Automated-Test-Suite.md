---
title: "HLD: Automated Test Suite"
date: 2026-05-07
tags: [hld, testing, quality]
story: "[[US-017: Automated Test Suite]]"
status: draft
---

## Overview

Add a `pytest`-based test suite that validates the schema, pipeline stage/promote functions, API routes, and IGDB matching logic without real credentials or network calls. Tests run against in-memory DuckDB instances and use `unittest.mock` to intercept HTTP requests.

## Goals & Non-Goals

**Goals**
- Schema correctness: all expected tables, columns, and seed data
- Pipeline correctness: stage + promote functions for all five platforms, including idempotency
- API smoke tests: key routes return expected status codes and shapes
- IGDB unit tests: lookup function returns correct values from mocked responses

**Non-Goals**
- Auth flows requiring real credentials (Xbox OAuth, PSN NPSSO, GOG, Switch)
- End-to-end browser/UI tests
- Performance or load testing

## Design

### Framework

| Component | Choice | Reason |
|---|---|---|
| Test runner | `pytest` | Industry standard; fixture system handles DB lifecycle cleanly |
| HTTP mocking | `unittest.mock.patch` | Zero extra deps; patches `requests.post/get` at call sites |
| FastAPI testing | `fastapi.testclient.TestClient` | Provided by FastAPI; no real server needed |
| Xbox title objects | `dataclasses` | Mirrors the pydantic shape without the `xbox` library dependency |

### File layout

```
tests/
  conftest.py          # shared fixtures (in-memory DB, mock secrets, test client)
  test_schema.py       # schema table/column/seed assertions
  test_pipeline.py     # stage + promote for all platforms, idempotency
  test_api.py          # GET /library, GET /setup, POST /sync, GET /api/library/columns
  test_igdb.py         # igdb_lookup_by_external_id unit tests
```

### Fixtures (conftest.py)

**`db_conn`** — `function`-scoped fixture that opens an in-memory DuckDB connection and runs `schema.sql` against it. Each test gets a fresh, isolated schema. Pipeline tests call stage/promote functions directly on this connection.

**`mock_secrets`** (session-scoped) — a minimal `gandalf.json`-shaped dict with a temp file, used to monkeypatch `db.load_secrets` / `db.SECRETS_PATH` so the FastAPI app and collect functions never touch the real file.

**`client`** — FastAPI `TestClient` wrapping the app, with the session cookie injected to simulate an authenticated user and `_WizardGate` bypassed via a patched `load_secrets` that always returns a valid Steam API key.

### Schema tests

Run `schema.sql` against a fresh in-memory DB and assert:
- All expected tables exist (`information_schema.tables`)
- Key columns exist (`information_schema.columns`) — `achievements.gamerscore_earned`, `achievements.gamerscore_total`, `library.purchase_source`
- `platforms` table has five rows with the correct slugs

### Pipeline tests

Each platform test follows the same pattern:

1. Call `stage_<platform>(conn, <mock_data>)` — assert staging table has expected rows and field values
2. Call `promote_<platform>(conn)` — assert rows appear in `games`, `platform_games`, `library`, and (where applicable) `achievements`
3. Call stage + promote a second time with identical data — assert row counts are unchanged (idempotency)

**Xbox-specific mocks**: `stage_xbox` expects objects with `.achievement` and `.title_history` attributes. A small `@dataclass` hierarchy in `conftest.py` mirrors the relevant fields (`title_id`, `name`, `achievement.current_achievements`, etc.) without importing the `xbox` library.

**Xbox achievement skip**: one test row has `achievements_total = 0`; assert no row is inserted into `achievements` for it.

**Xbox `purchase_source`**: after `promote_xbox`, assert every `library` row for platform_id=5 has `purchase_source = 'unknown'`.

### API tests

The FastAPI app calls `load_secrets()` and `init_db()` at module level. To isolate this, tests patch both before importing `main`. A `pytest` fixture handles the patching order.

| Route | Assertion |
|---|---|
| `GET /library` | 200, user in context |
| `GET /setup` | 200, connected/disconnected flags match patched secrets |
| `POST /sync` (idle) | 302 redirect to `/logs`, `_sync_running` stays False (background thread not started in test) |
| `POST /sync` (running) | 302 redirect to `/logs` without starting a second sync |
| `GET /api/library/columns` | 200, JSON contains `platform` and `groups` keys |

### IGDB tests

Patch `requests.post` to return a mock response object:

- Match found: response body `[{"game": 42}]` → function returns `42`
- No match: response body `[]` → function returns `None`
- HTTP error: response `.ok = False` → function returns `None`

## Data & Privacy Considerations

- All tests use fabricated data; no real Steam IDs, PSN IDs, or game titles from a real account
- The `mock_secrets` fixture writes to a temp file that is deleted after the test session; it must never be placed in the project root where it could be mistaken for `gandalf.json`

## Open Questions

- Should idempotency tests be a parametrised fixture covering all five platforms, or kept as separate test functions? (Parametrise is cleaner but harder to debug individually — preference TBD during implementation.)
- `POST /sync` starts a background thread via `BackgroundTasks`; the `TestClient` may execute it synchronously. Need to verify whether `_sync_running` state is observable in the test or whether the assertion should simply check the redirect URL.
