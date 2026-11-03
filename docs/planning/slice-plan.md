# Slice Plan and Cost Model

## Prerequisites (outside this repo)

| # | Prerequisite | Needed for | Who |
|---|---|---|---|
| P1 | Arthur OKs Phases 1, 2 and 5, and verifiers v1 (ADR-002) | Slice 1 | Arthur |
| P2 | The GitHub repo exists | Pushing anything | Arthur |
| P3 | OK for Ollama and three models, about 7 GB (ADR-010) | Spike 3, slice 4 | Arthur |
| P4 | A Prime Intellect account, terms accepted | Slice 5 | Arthur |
| P5 | A written budget and cap for GPUs (ADR-011) | Slice 7 | Arthur |

## Spikes (local, $0)

| # | Question | Method | Pass | Time |
|---|---|---|---|---|
| 1 | Does verifiers v1 work here? | Install the pinned version in a fresh venv (report the download size first); a toy Taskset whose Toolset points at a local MCP server; find the working eval command; confirm `--no-push` sends nothing; read `sql-agent-gym`'s code if public | A toy rollout scores; header auth answered; nothing uploaded | 1.5 h |
| 2 | Does the harness's compose take a newer MCP-backbone? | Build it by git context with the pin at current `main`; seed two extra workspaces; measure memory | Tools answer; fingerprints match the harness's; memory known | 1 h |
| 3 | How fast is a local model? | Ollama with Qwen3 1.7B; 5 rollouts of the toy task through the OpenAI endpoint | Tool calls parse; time per rollout known; full baseline time estimated | 1 h |
| 4 | Do the data copies change the answers? | Draft the copy script; run the 40 reused gold queries on stock, A and B | Every answer differs between A and B, or the script is adjusted | 1 h |

## Slices

**Evaluation-driven order, as in Juku and Project 9:** the checks come
first and fail, then the code is written until they pass. Each new test is
mutation-checked once. Each slice updates `docs/guide.md`.

| Slice | Delivers | Done when | Cost |
|---|---|---|---|
| **1. Stack, copies, reused tasks** | Scaffold (uv, ruff with complexity rules, pyright strict, CI, README with layout, guide); compose on the harness's repro; the copy script; the 40 reused tasks in the harness's format; task checks C1–C7 | See below | $0 |
| **2. Environment and reward** | Taskset, Toolset, `submit_answer`, the rewards and metrics (ADR-005); the honest policy and the cheat suite (ADR-006); fingerprints before and after | Honest policy scores 1.0 on all 40; every cheat ≤ 0 on all 40; CI runs it against the compose | $0 |
| **3. New tasks and held-out** | 60 new tasks; splits; canary; held-out file kept outside the repo; Arthur's sample review; the agreement test with the harness (G5) | All 100 pass C1–C7; the suite passes on all 100; G5 passes | $0 |
| **4. Baselines** | Three models on dev, then held-out once; run records; generated results table; top-20 rollouts read for new cheats | G4 met; every number traces to a record; any new cheat is a cheat policy | $0 (electricity) |
| **5. Publish** | README and guide final; MIT licence; `prime env push` from Arthur's account | Installs and runs on a clean venv from the Hub; G6, G7 | $0 |
| **6. Evidence and write-up** | JOURNEY; portfolio entry (with the portfolio session) | A privacy check passes; every claim traces to a file | $0 |
| **7. Training (optional, paid)** | prime-rl config; rented GPUs; re-measured baseline; one run; held-out once | G9 met or reported as not met; spend under the cap | Up to $30, not approved |

## Slice 1 in detail: the first slice

**Scope:** local Docker and Python. No model, no network beyond pulling the
pinned images and Pagila, no account. It can start the moment Arthur OKs
the plan.

**Delivers:**
- `pyproject.toml` (uv, Python 3.12), ruff with `C901` (max 10) and
  `PLR0911`/`PLR0912`/`PLR0913`/`PLR0915`, pyright strict;
- `.github/workflows/ci.yml`, README with a layout section, `docs/guide.md`;
- `compose.yaml`: the harness's repro by git context at a pinned commit,
  plus our `copies` service;
- `anaylisists/data/make_copies.sql`: the seeded copy script;
- `tasks/public.yaml`: the 40 reused tasks, with `family`, `split`,
  `ordered`, a second SQL and a wrong reading each;
- `tests/test_task_checks.py`: C1–C7 for every task.

**Order:**
1. Write the task checks and the 40 tasks. Tests fail (no stack yet).
2. Bring up the compose and the copies. Make C1–C7 pass.
3. Spend a pass trying to break it: an empty copy, a copy with a wrong
   fingerprint, a gold query with a tie, a task whose answer doesn't change
   between copies, a restart halfway through setup.

**Done when:**
- all 40 tasks pass C1–C7, or are rewritten until they do;
- each fingerprint is stored and checked;
- CI is green, and the new tests are mutation-checked;
- the guide's flow covers setup, from `docker compose up` to a task check.

**Branch:** `feat/stack-and-tasks`, from `main`, once `docs/planning` is
merged.

## Cost model

| Item | v1 (slices 1–6) | Slice 7, if approved |
|---|---|---|
| Models | $0: local, through Ollama | — |
| Compute | $0: this Mac | About $23–28 for 2 × H100, about 4 hours (ADR-011) |
| Hosting | $0: nothing hosted; the Hub listing is free as far as found | — |
| Prime trace uploads | $0: `--no-push` always | Small; with Arthur's OK only |
| Downloads | About 7 GB of models, plus images and a 13 MB Pagila | — |
| **Hard cap** | **$0** | **$30 recommended** |

**Nothing in slices 1 to 6 costs money.** No Sumopod balance is used by
this project at any stage.
