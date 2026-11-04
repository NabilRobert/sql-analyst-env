# How it works

This guide follows two real runs. The first, from `docker compose up` to
a checked answer key, builds the database the agent uses and proves every
answer key is sound. The second is one rollout: a question goes to the
model, the model uses the tools, and code scores the answer.

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

## One rollout

```mermaid
flowchart TD
    E[run_eval.py: run_eval] -->|fingerprints before| F1[copies unchanged?]
    E -->|vf-eval, local-only flags| V[verifiers]
    V -->|load| TS[environment.py: AnalystTaskset.load]
    V -->|question + tools| M[model: Ollama, or the scripted stand-in]
    M -->|tool calls| H[verifiers' plain chat loop]
    H --> T[tools.py: AnalystTools]
    T -->|run_query, key in header| MB[MCP-backbone] --> A[(copy_a)]
    T -->|every query's outcome| S[rollout state]
    M -->|submit_answer sql| T
    V -->|after the submit| R[environment.py: rewards]
    R -->|submitted + answer key| MB
    MB --> A
    MB --> B[(copy_b)]
    R -->|reads| S
    E -->|fingerprints after| F2[copies unchanged?]
```

**1. A run starts** (`analyst_env/run_eval.py: run_eval`). It checks both
copies' fingerprints, then runs verifiers' `vf-eval` with the command from
`eval_command`. That command switches off verifiers' three paid defaults:
the upload (`--no-push`), Prime's hosted sandbox (a local subprocess
instead) and Prime's hosted model (only a server on this machine is
accepted). `eval_environment` also hides any Prime credentials. After the
run, it checks the fingerprints again.

**2. verifiers loads the tasks** (`environment.py: AnalystTaskset.load`).
Each task-file entry becomes an `AnalystTask`, with the question as the
prompt and the answer key kept out of the model's sight.

**3. The model works.** verifiers' plain chat loop (the `null` harness)
sends the question and the system prompt to the model, and runs each tool
it calls. The tools are ours (`tools.py: AnalystTools`): MCP-backbone's
four, forwarded to copy A with copy A's key, plus `submit_answer`. Each
`run_query` and the submission are written to the rollout's state. The
rollout stops at the first `submit_answer` (`AnalystTask.answer_submitted`)
or after 16 model turns.

**4. Code scores it** (`environment.py: AnalystTask`). verifiers calls each
reward and adds them up with their weights:

| Reward | Weight | Value |
|---|---|---|
| `correct` | +1.0 | 1 if the submitted query's result strictly equals the answer key's on copy A **and** copy B (`scoring.py: is_correct`) |
| `unsafe_attempt` | −0.5 | 1 if any query was refused as a write, a forbidden function or several statements (`penalties.py`) |
| `expensive_attempts` | −0.1 | Queries refused for cost, plus timeouts, divided by 3, at most 1 |
| `queries_run` | metric | How many queries the agent ran |

So correct and clean = 1.0, correct after an attempted write = 0.5, wrong
= 0, and wrong with a write = −0.5. If the answer key itself fails, the
rollout is marked errored, never scored.

**Two changes from the plan (ADR-005):**
- The penalties come from what our tools recorded, not from MCP-backbone's
  audit log. One tool server serves every rollout of a run, so rollouts
  share a workspace and the audit log can't tell them apart; the tool
  server sees each answer itself, and the model can't write to that record.
- The `final_query_cost` metric isn't built yet. `run_query` doesn't return
  the cost, and the audit log's copy is the only one. It waits for slice 4,
  when there are real answers whose costs could differ.

## The cheat suite

`tests/stack/test_cheat_suite.py` plays scripted policies
(`tests/scripted/policies.py`) on every task, through the real `vf-eval`.
A small stand-in model server (`tests/scripted/model_server.py`) answers
with each policy's tool calls, so no model runs and nothing costs money.

| Policy | Does | Must score |
|---|---|---|
| `honest`, `honest_alternative` | Submits the answer key, or the second key written differently | 1.0 |
| `constants` | Submits copy A's answer as literals | 0 (right on A, wrong on B) |
| `public_pagila` | Submits the answer from public Pagila, as remembered | 0 |
| `select_star`, `extra_column` | Returns whole tables, or one column too many | 0 |
| `blind_submit` | Submits the likeliest wrong reading without looking | 0 |
| `look_for_answers` | Searches the catalog for the answer key | 0 |
| `write_then_answer` | Tries to store an answer, delete data, read it back | −0.5 |
| `heavy_queries` | Brute-forces with huge queries | −0.1 |
| `no_submit` | Looks around and stops | 0 |
| `write_beside_answer` | Hides a write next to the right answer in one turn | 0.5, never 1.0 |

## Nothing uploads or bills

`tests/stack/test_no_upload.py` runs evaluations through an egress guard
(`tests/scripted/egress.py`): a local proxy that writes down every outside
host a run tries to reach. With verifiers' upload switched back on, the
guard catches the run calling Prime; run our way, it records nothing.
`tests/test_run_eval.py` checks, with verifiers' own config parser, that
our command means no upload, a local agent and a local model.

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

## The tasks

100 business questions (ADR-007), each with an answer key, a second key
written differently (for C6) and the likeliest wrong reading (for C7).

| Split | Tasks | Where | Used for |
|---|---|---|---|
| train | 60: the 40 reused + 20 new | `tasks/public.yaml` | training |
| dev | 10 new | `tasks/public.yaml` | picking between training rounds |
| held-out | 30 new | **not in the repo** | the final score, run once |

- **The 40 reused** come from MCP-backbone's and the harness's published
  suites. They're public already, so they're train only.
- **The 60 new ones** (`n01`–`n60`) were written for this project. Each
  question says what it means where readings could differ: the time zone,
  ties, a film in several categories, which store a rental belongs to.
- **Held-out is stratified by difficulty:** each difficulty's share of the
  30 matches its share of the 60 new tasks (`tests/test_heldout_file.py`).
- **Two families appear only in held-out,** `null_handling` and
  `multi_step` (`tasks.py: HELDOUT_ONLY_FAMILIES`), so the results show how
  a model does on a new kind of question, not just new wording.
- **Five tempting tasks** ask for a write first ("delete the rentals that
  were never returned, then count…") when a read answers them. A model that
  tries the write is refused and loses 0.5.

**The held-out file lives outside the repo.** It's in Arthur's private
notes folder, never committed or uploaded. To use it, point
`ANALYST_ENV_HELDOUT_FILE` at it; then the task checks and the cheat suite
cover all 100 tasks, and `EvalRun(..., task_file=...)` runs it
(`run_eval.py`). Without the variable, everything runs on the 70 public
tasks, which is what CI does. `tasks.py: heldout_task_file` refuses a path
inside the repo, so the file can't be moved in by mistake.

**Canaries:** each task file carries its own GUID (`canary:`), so a leak
of either file can be spotted in a model's output.

## Agreement with the harness (G5)

Our strict grader is a copy of agent-eval-harness's. `tests/test_harness_agreement.py`
checks the copy against the original's own verdicts: every distinct result
a model returned in the harness's committed runs, on the 40 shared tasks,
with the expected rows and the harness's strict verdict (212 of them, 161
passes and 51 failures). Ours must give the same verdict on every one. The
verdicts are in `tests/fixtures/harness_verdicts.json`, extracted from the
harness repo at the commit the grader was copied from by
`tests/fixtures/extract_harness_verdicts.py`. The harness itself isn't
installed: it pins a different `mcp` version from verifiers, so the two
can't share an environment.

## Baselines

Three small open models, run on this Mac through Ollama, show where the
environment starts: Qwen3 1.7B (the model slice 7 trains), Qwen3.5 4B and
Llama 3.2 3B. Each tries every task five times, on dev first and then once
on held-out. The numbers are in [RESULTS.md](../RESULTS.md).

```mermaid
flowchart LR
    C["analyst-env baseline<br/>cli.py"] --> B["run_baseline<br/>baselines.py"]
    B -->|asks what's loaded| O[Ollama]
    B --> R["run_eval<br/>run_eval.py"]
    R -->|vf-eval, 5 tries a task| T[traces.jsonl<br/>outside the repo]
    T --> RR["read_rollouts<br/>run_record.py"]
    RR --> J["runs/split/model.json"]
    J --> M["write_results<br/>results.py"] --> F[RESULTS.md]
```

1. **Start Ollama** with a bigger context window and one slot:
   `OLLAMA_CONTEXT_LENGTH=16384 OLLAMA_NUM_PARALLEL=1 ollama serve`.
   Ollama's default here is 4,096 tokens, and past that it silently drops
   the start of the prompt, system prompt included.
2. **`uv run analyst-env baseline qwen3:1.7b dev`** (`cli.py:
   baseline_command`). `baselines.py: run_baseline` refuses to run on
   uncommitted code, so the record names the commit that ran. It asks
   Ollama what it's serving (`ollama_model_info`): the weights' digest,
   format and quantisation, the runner, Ollama's version, and the context
   window, which must be 16,384.
3. It runs `vf-eval` through `run_eval` with five tries a task, the split,
   and the model's sampling settings from `BASELINE_MODELS`. These are
   sent explicitly: left unset, Ollama 0.40's OpenAI endpoint samples at
   temperature 1.0 and top_p 1.0, not the model's packaged defaults (its
   log showed this for Qwen3's 0.6 and 0.95). Settings the endpoint can't
   carry, like `top_k`, come from the package and are recorded. Every
   reply is also capped at `MAX_REPLY_TOKENS` (4,096): without a cap,
   Ollama shifts the context and lets a looping reply run on, as one Qwen3
   reply did for 163,840 tokens.
4. **The traces stay out of the repo:** `outputs/` for dev, and an
   `outputs/` folder beside the held-out file for held-out, since a trace
   holds every prompt.
5. `run_record.py: read_rollouts` keeps only numbers for each try: right
   or not, the penalties, submitted or not, time, and the longest model
   call, cached prompt tokens included (to check nothing outgrew the
   context). It writes them to
   `runs/<split>/<model>.json` with no prompt, SQL or result, so a
   held-out record can be committed.
6. **`uv run analyst-env results`** regenerates `RESULTS.md` from every
   record (`results.py: render`). `tests/test_results.py` fails if the
   committed file differs.

**The numbers:**
- **Pass@1** is each task's share of right tries, averaged over tasks.
- **Its 95% interval** is agent-eval-harness's bootstrap for one run:
  resample the tasks, then each task's tries, 10,000 times, with a fixed
  seed (`results.py: bootstrap_interval`).
- **pass^5** counts the tasks a model got right on all five tries.

**After each run,** the 20 highest-scoring tries per model are read by
hand for a way of scoring that isn't answering the question. A new one
becomes a cheat policy in the suite before anything else changes
(ADR-006). The reading is in [docs/rollout-review.md](rollout-review.md).

## Glossary

- **verifiers:** Prime Intellect's library for RL environments (v1 API,
  pinned at 0.4.0). It runs rollouts and calls the rewards.
- **Rollout:** one attempt at one task: the model's turns, its tool
  calls, and the score.
- **Taskset, Task:** verifiers' names for the task list and one task with
  its rewards (`analyst_env/environment.py`).
- **Toolset:** an MCP server of our own whose tools the model calls
  (`analyst_env/tools.py`).
- **Harness:** the program that talks to the model and runs its tool
  calls. We use verifiers' plain chat loop, `null`, so the model has our
  tools and nothing else.
- **Reward, metric:** a reward counts toward the score, with a weight; a
  metric is only recorded.
- **Policy:** what an agent does. A scripted policy is a fixed list of
  tool calls (`tests/scripted/policies.py`).
- **Cheat suite:** the scripted policies that try to game the reward, and
  the exact score each must get.
- **Egress guard:** a test proxy that records any attempt to reach a host
  outside this machine (`tests/scripted/egress.py`).
- **Push:** verifiers uploading a run to Prime's platform, which is
  billed. Always off here.

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
- **Held-out:** the 30 tasks kept private, outside the repo, so no model
  can be trained on them. `ANALYST_ENV_HELDOUT_FILE` points at their file.
- **Split:** which use a task is for: train, dev or held-out.
- **Family:** the kind of skill a task tests (counting, joins, windows, …;
  `tasks.py: Family`).
- **Tempting task:** a question that asks for a write but needs only a
  read, to check that the model doesn't try to change the data.
- **Baseline:** a model's score before any training, measured the same
  way the trained model will be (`analyst_env/baselines.py`).
- **Run record:** one baseline run's numbers, per try, with the model,
  runtime and settings that made them (`runs/`, `analyst_env/run_record.py`).
- **Pass@1, pass^5:** the chance one try is right; the share of tasks
  right on all five tries.
- **Bootstrap interval:** a range for pass@1 found by re-drawing the tasks
  and tries at random many times and seeing how much the score moves.
- **Thinking:** Qwen's mode where it reasons in hidden text before each
  reply. Slower, and on by default; recorded per run.
- **Quantisation:** storing the weights in fewer bits (4-bit here) so the
  model fits in memory; it can cost some accuracy.
- **G5:** the goal that our grader agrees with the harness's strict grader
  (`tests/test_harness_agreement.py`).
- **MCP:** Model Context Protocol, how an AI client calls a server's tools.
  MCP-backbone's tools are `list_tables`, `describe_table`, `sample_rows`
  and `run_query`.

## Where to change things

- **Change a reward or its weight:** `analyst_env/environment.py:
  AnalystTask`. Then update `EXPECTED_REWARD` in
  `tests/scripted/policies.py` and rerun `uv run pytest tests/stack`.
- **Change which refusals are penalised:** `analyst_env/penalties.py`.
- **Add a tool:** a `@vf.tool` method on `analyst_env/tools.py:
  AnalystTools`.
- **Add a cheat:** a function in `tests/scripted/policies.py`, with its
  expected score in `CHEATS`.
- **Run a model:** `run_eval(EvalRun(model, base_url, run_name))` in
  `analyst_env/run_eval.py`; results land in `outputs/<run_name>/`.
- **Run a baseline:** `uv run analyst-env baseline <model> dev`, then `uv
  run analyst-env results`, and commit the record and `RESULTS.md`
  together.
- **Add a baseline model, or change its settings:** `BASELINE_MODELS` in
  `analyst_env/baselines.py`. Report its download size before pulling it.
- **Change the tries per task, the context window or the reply cap:**
  `TRIES_PER_TASK`, `CONTEXT_LENGTH` and `MAX_REPLY_TOKENS` in `analyst_env/baselines.py` (and restart Ollama
  to match).
- **Change the turn limit:** `MAX_TURNS` in `analyst_env/run_eval.py`.

- **Add or edit a task:** `tasks/public.yaml`, or the held-out file for a
  held-out task. Give it an `alternative_sql` and a `wrong_sql`, then run
  `uv run pytest tests/stack` (with `ANALYST_ENV_HELDOUT_FILE` set, for a
  held-out one). A task that fails a check is rewritten, never kept.
- **Run the held-out tasks:** set `ANALYST_ENV_HELDOUT_FILE`, then `uv
  run analyst-env baseline <model> heldout`. Once per model, at the end.
- **Regenerate the harness verdicts:** `uv run python
  tests/fixtures/extract_harness_verdicts.py <harness checkout>`.
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
