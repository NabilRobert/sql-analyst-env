# How it works

This guide follows one real run, from `docker compose up` to a checked
answer key. Slice 1 has no model yet: it builds the database the agent will
use and proves every answer key is sound.

## The flow

```mermaid
flowchart TD
    U[docker compose up -d --wait] --> DB[(Postgres, UTC)]
    U --> S[setup: stack/setup_stack.py]
    S -->|download at a pinned commit| P[(pagila)]
    P -->|CREATE DATABASE ... TEMPLATE| A[(copy_a)]
    P -->|CREATE DATABASE ... TEMPLATE| B[(copy_b)]
    S -->|make_copies.sql, seed A / seed B| A
    S -->|make_copies.sql, seed A / seed B| B
    S -->|one workspace + key per copy| K[/out/keys.json]
    U --> M[MCP-backbone on 127.0.0.1:8766]
    T[uv run pytest] --> F[fingerprint each copy]
    F -->|matches stack/fingerprints.json?| C[check every task: C1 to C7]
    C -->|run_query, key in header| M
    M --> A
    M --> B
```

**1. The stack starts** (`compose.yaml`). Three services:
- `db`: Postgres 16 with the time zone set to UTC, so date answers don't
  depend on the machine.
- `setup`: runs once, in the MCP-backbone image. The image is built from
  agent-eval-harness's `repro/` folder, fetched by git at a pinned commit,
  with MCP-backbone pinned to a newer commit.
- `mcp`: MCP-backbone itself, published on `127.0.0.1:8766` only.

**2. Setup builds the data** (`stack/setup_stack.py: main`).
1. `load_pagila` downloads Pagila at the commit the harness's published runs
   used, with MCP-backbone's own loader.
2. `make_copy` clones it twice and runs `stack/make_copies.sql` on each,
   with that copy's settings from `COPIES`. The script deletes a seeded few
   percent of films, customers, rentals and actor credits, shifts lengths
   and some ratings and returns, scales payments, and adds a few countries,
   actors and Canadian cities. A hash of the seed and each row's id decides
   which rows, so the same seed always makes the same copy.
3. `provision_roles` gives each copy its own read-only login, with
   MCP-backbone's script.
4. `seed_workspaces` makes one MCP-backbone workspace per copy, with raised
   limits, and writes the keys to the stack's own volume (never the host).

**3. The checks run** (`uv run pytest`).
1. `tests/stack/conftest.py: stack_keys` reads the keys with
   `docker compose exec` (`analyst_env/backbone.py: read_stack_keys`).
2. `analyst_env/task_checks.py: check_tasks` opens one MCP session per copy
   (`backbone.py: open_copies`). The key goes in the `Authorization` header.
3. It fingerprints both copies (`fingerprint.py: mismatched_copies`) and
   stops if either differs from `stack/fingerprints.json`.
4. `check_task` runs each task's queries through `run_query` on both copies,
   four tasks at a time, and returns every failed check.

## The seven checks

Every task must pass all of them on both copies (`task_checks.py`):

| | Check | Catches |
|---|---|---|
| C1 | The gold SQL passes MCP-backbone's validator and cost check | An answer key the agent could never run |
| C2 | It returns the same result twice | A random answer |
| C3 | Re-sorting ties both ways doesn't change it | "Top 3" when the 3rd and 4th tie |
| C4 | At least one row, and not cut off at 200 | An empty or truncated answer |
| C5 | The two copies give different results | A task a constant could pass |
| C6 | A second, separately written query agrees | A wrong answer key |
| C7 | The likeliest wrong reading disagrees, and runs | An ambiguous question |

## Glossary

- **Task:** one business question with its answer key, in `tasks/*.yaml`
  (`analyst_env/tasks.py: Task`).
- **Gold SQL** (`reference_sql`): the query whose result is the right
  answer. The result is what counts, not the SQL text.
- **Copy A, copy B:** two perturbed versions of Pagila. The agent will see
  A; grading will also use B. Made by `stack/make_copies.sql`.
- **Perturbed:** changed on purpose, by a seeded script, so memorised
  answers from public Pagila are wrong.
- **Fingerprint:** a hash of a copy's data (`analyst_env/fingerprint.py`).
  If it changes, every answer may change, so checks refuse to run.
- **Workspace:** MCP-backbone's unit of access: a key, limits and one
  database. Here, one per copy.
- **Strict match:** same columns in the same order, exactly equal values,
  rows in any order (`analyst_env/grading.py: rows_equal_strict`).
- **Canary:** a GUID in every task file, so leaked tasks can be spotted in
  a model's training data.
- **Held-out:** tasks kept private, in `tasks/private/`, so no model can be
  trained on them.
- **MCP:** Model Context Protocol, how an AI client calls a server's tools.
  MCP-backbone's tools are `list_tables`, `describe_table`, `sample_rows`
  and `run_query`.

## Where to change things

- **Add or edit a task:** `tasks/public.yaml` (or `tasks/private/` for
  held-out). Give it an `alternative_sql` and a `wrong_sql`, then run
  `uv run pytest tests/stack`.
- **Change how the copies differ:** `stack/make_copies.sql` and `COPIES` in
  `stack/setup_stack.py`. Then `docker compose down -v`, `docker compose up
  -d --wait`, `uv run analyst-env fingerprint --write`, and rerun the
  checks: every task's answers change.
- **Move a pin:** MCP-backbone and the harness image in `compose.yaml`;
  Pagila's commit in `compose.yaml`'s `PAGILA_COMMIT`.
- **Point at a different local port:** set `ANALYST_ENV_MCP_URL`. Anything
  not on this machine is refused (`backbone.py: ensure_local`).
- **Check more tasks at once:** `PARALLEL_TASKS` in
  `analyst_env/task_checks.py`.
