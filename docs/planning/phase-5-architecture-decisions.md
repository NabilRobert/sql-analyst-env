# Phase 5: Architecture Decisions

Short ADRs, 2026-11-03. **Settled** ones were decided with Arthur. The rest
are recommendations, open until he agrees. The summary table, the first
slice and the open questions are at the end.

```
task files (public + private held-out)
        │
        ▼
verifiers v1 Taskset ──prompt──► model (Ollama, local)
        │                               │ tool calls
        │ Toolset (MCP over HTTP) ◄─────┘
        ▼
MCP-backbone, pinned, local ──► copy A (perturbed Pagila, what the agent sees)
        │                  └──► copy B (hidden, grading only)
        ▼
audit log (bookkeeping DB) ──► rewards: correct on A and B, minus penalties
        │
        ▼
run records ──► results table (generated)      spans ──► agent-observability (opt-in)
```

## Reuse map (the folder's "reuse before building" rule)

Arthur's repos were searched first. MCP-backbone and agent-eval-harness
already hold most of what this needs, except the RL side.

| Part | Reused | Built (and why) |
|---|---|---|
| Environment and rollout loop | **verifiers v1** (ADR-002) | The Taskset, the submit tool, the rewards |
| Tools, validator, cost check, read-only role, audit log | **MCP-backbone**, unchanged, at a pinned commit (ADR-004) | — |
| Local Postgres + MCP-backbone + Pagila at a pinned commit | **agent-eval-harness's `repro/`** compose and image, by git build context (ADR-004) | A step that makes copies A and B |
| 40 Pagila tasks with reference SQL | **MCP-backbone's 30 + the harness's 10**, in the harness's suite format (ADR-007) | 60 new tasks |
| Strict result grader | **The harness's `rows_equal_strict`**, grader v4, copied with attribution (ADR-008) | — |
| Expected answers and data fingerprints | **The harness's `generate-expected` pattern** (ADR-008) | Run per data copy |
| Confidence intervals and a generated results table | **The harness's report code**, as a dev dependency (ADR-014) | — |
| Scripted agents for CI | **The harness's scripted and gullible agents**, as the pattern (ADR-006) | The cheat policies |
| Spans | **agent-observability's** conventions; MCP-backbone already emits spans (ADR-012) | One span per rollout |
| Local models | **Ollama** and open models (ADR-010) | — |
| Training (slice 7) | **mlx-lm** LoRA on the Mac; Project 14's planned setup (ADR-011) | Picking verified rollouts |
| Perturbed data copies | Nothing fits: the copies must keep Pagila's schema and keys while changing answers | **Built:** a short seeded SQL script; this is part of what's shown |
| Reward, cheat suite, task checks | Nothing fits | **Built:** this is what the project demonstrates |

## ADR-001: Name (settled)

**Decision:** `sql-analyst-env`, for the folder, the repo and the Hub
listing. Arthur, 2026-11-04: "why not".

**History:** the name changed twice before this, both times by mistake.
1. On 2026-11-03 it was recorded as `anaylisists`, from Arthur's answer to
   the name question.
2. Later that day it became `flight-analysts`, from a relayed message read
   as asking for it. Arthur, 2026-11-04: "no flight anything the name is
   just AI Flight School", meaning that's Project 10's name, not this one's.
The folders and docs were renamed after slice 2, and again during slice 4.

**Rejected:** `rl-analyst-env`, `pagila-analyst-env`.

## ADR-002: verifiers v1, published on the Environments Hub (settled)

**Decision:** build on Prime Intellect's `verifiers`, the **v1 API**
(`import verifiers.v1 as vf`), pinned to an exact version, published
publicly on the Environments Hub in slice 5 from an account Arthur creates.
Arthur approved the framework and publishing on 2026-11-03.

**Prime's terms** (updated 2026-10-12): Arthur keeps ownership; Prime's
licence is only to provide the service; Prime won't train on the content;
the licence chosen at publication governs others' use. New York law,
arbitration in San Francisco. Not legal advice.

**What was checked** (primary sources, 2026-11-03):
- **Licence:** MIT (`LICENSE` and `pyproject.toml`). Python 3.11 to 3.14.
- **Maintained:** 0.4.0 on 2026-10-12, then 0.3.1, 0.3.0, 0.2.1 and 0.2.0
  since July, plus dev builds most days. About 38 commit authors in six
  months, most from 3 or 4 Prime staff. 4.8k stars.
- **v0 is gone.** 0.4.0 removed `SingleTurnEnv`, `ToolEnv`, `MultiTurnEnv`,
  `Rubric` and `Parser`. The Hub tags v0 environments "Legacy". Every SQL
  environment on the Hub today is v0 (ADR-003).
- **v1 shape:** a `Taskset` returns `Task`s. Rewards are methods marked
  `@vf.reward(weight=…)`, summed into the trace's reward. `@vf.metric` or
  weight 0 logs without training on it. A `Toolset` can point at an existing
  streamable-HTTP MCP server by `url`, which is exactly MCP-backbone.
- **Mac:** no torch or vLLM dependency for the environment side. Training
  (prime-rl) needs Linux and an NVIDIA GPU.

**Traps found in the docs:**
- **v1 evaluation uploads traces to Prime's platform by default.** Prime
  bills $1 per GiB uploaded plus storage. Every run here passes `--no-push`,
  and the run script refuses to start without it.
- **The docs disagree on the command.** `vf-eval` is gone from `main`, and
  Prime's docs still name it in places. Spike 1 finds the working command
  at the pinned version.
- **Churn:** 0.4.0 removed a whole API three weeks ago. So the pin is exact,
  and an upgrade is its own commit with the cheat suite rerun.

**Rejected:**

| Option | Why not |
|---|---|
| verifiers v0 | Removed in 0.4.0; the Hub calls it deprecated |
| An Inspect AI task (Arthur's usual eval stack) | Inspect evaluates; it isn't a training environment, and the Hub doesn't take it. agent-eval-harness already covers evaluation |
| SkyRL's environment format | Apache-2.0 and good, but not what the Hub runs, so no audience in one step |
| Gymnasium | No notion of chat, tools or LLM rollouts |
| Writing a rollout loop | The framework is the point of reuse; the rewards are the work |

## ADR-003: Where it stands against existing work

**Text-to-SQL RL isn't new; the combination here is.**

| Existing | What it rewards | Overlap |
|---|---|---|
| `vedant/sql-agent-gym` (Hub, v0) | A layered trace-plus-state verifier that fails a cheating agent a naive one passes; tagged anti-reward-hacking | **Closest, on reward hacking.** From the Hub's search listing only: its page renders in a browser, and its code wasn't read |
| `mikqu/mcp-sqlite` (Hub, v0) | Questions over a messy SQLite database through MCP, graded by a model | Close on MCP; uses a judge |
| `isk/crm-sql` (Hub, v0) | Business questions over a synthetic CRM | Close on "business analyst" |
| `primeintellect/skyrl-sql` (Hub, v0), SkyRL-SQL (Apache-2.0) | −1 bad format, 1 result match, else 0; SQLite, Spider and SynSQL | Same core reward |
| Arctic-Text2SQL-R1 (Apache-2.0, arXiv 2505.20315) | 1 exact match, 0.1 executable, else 0; argues richer rewards invite hacking | Same core reward |
| SQL-R1 (Apache-2.0) | Execution, length, syntax and format (as summarised in the Arctic paper; secondary) | — |

**What none of them has, from what could be read:** Postgres behind a
production-style MCP server with a validator, a cost check and an audit
log; safety and cost penalties on top of the match; hidden data copies; and
the v1 API.

**Consequence:** the README cites `sql-agent-gym` and says what's different,
rather than claiming the anti-hacking idea as new. Spike 1 reads its code
if it's public.

## ADR-004: The agent talks to a local, pinned MCP-backbone over HTTP

**Decision:**
- The `Toolset` connects to MCP-backbone at a local URL, with the workspace
  key in the `Authorization` header. If `Toolset(url=…)` can't send a
  header (spike 1), a small Toolset of `@vf.tool` methods forwards each call
  with the MCP client instead.
- **The stack is agent-eval-harness's `repro/` compose**, reached by git
  build context at a pinned commit, not copied. It already loads Pagila at
  the commit the published runs used, provisions the read-only role,
  migrates the bookkeeping database, and seeds a workspace with raised
  limits, all with MCP-backbone's own scripts.
- On top, one setup service of our own makes copies A and B (ADR-009) and
  seeds one workspace per copy, and one per parallel rollout slot.
- **The MCP-backbone pin moves to current `main`.** The harness pins
  `4e418e9`, from before the retry-and-audit fix (#14). Spike 2 checks the
  newer commit in the same compose.
- **Pagila stays at the harness's pinned commit, on Postgres 16.** Pagila's
  current master says it's tested on Postgres 18 and needs pgvector. Its
  licence is the PostgreSQL License (switched from MIT text on 2026-10-08;
  both are permissive). The data is downloaded at setup, not redistributed.
- **The environment refuses any non-local MCP address** (E4).

**Rejected:**
- *The live server:* 5 queries per hour per workspace, and the small shared
  server isn't for strangers' training runs.
- *Importing MCP-backbone in the same process:* verifiers pins `mcp==2.0.0`;
  over HTTP, the two never share dependencies, and it's what a real client
  does.
- *A SQLite copy:* loses the validator, cost check and audit log, which are
  the point.
- *verifiers' paid `prime` sandbox:* local Docker does the same at $0.

## ADR-005: The reward

**Decision:** the model ends a rollout by calling `submit_answer(sql)`.

| Reward | Weight | Value |
|---|---|---|
| `correct` | **+1.0** | 1 if the submitted SQL's result strictly equals the gold result on copy A **and** copy B, else 0 |
| `unsafe_attempt` | **−0.5** | 1 if any query in the rollout was refused by the validator (a write, a forbidden function, several statements) |
| `expensive_attempts` | **−0.1** | Refusals for cost plus timeouts, divided by 3, at most 1 |
| `final_query_cost` | 0 (metric) | The submitted query's cost estimate divided by the gold query's |
| `turns`, `tool_calls` | 0 (metric) | Counts |

**So:** correct and clean = 1.0; correct after one attempted write = 0.5;
wrong and clean = 0; wrong with a write = −0.5. Getting it right always
matters most, and trying to write always costs.

Penalties come from the **audit log**: each parallel slot has its own
workspace, so a rollout's rows are that workspace's rows in its time
window. MCP-backbone's `run_query` response doesn't return the cost; the
audit row has it, so no change to MCP-backbone is needed.

An infrastructure failure raises, so the rollout is marked errored, never
scored (verifiers' own advice, and O1).

**Rejected:**
- *Correctness only* (SkyRL, Arctic): no safety signal, which is the point
  of this environment.
- *Partial credit for SQL that runs* (Arctic's 0.1): easy to farm, and the
  Arctic paper itself warns about it.
- *A cost penalty from the start:* it could teach the model to skip a join
  it needs. It's a metric in v1 and becomes a reward only if the baselines
  show cost varies among correct answers.
- *Multiplying correctness by a safety factor:* a wrong answer would then
  carry no safety signal at all.
- *Grading the prose answer:* needs a judge (ADR-008).

## ADR-006: Reward hacking, and the cheat suite

**How a model could game the reward, and what stops each:**

| # | Cheat | Defence | Tested by |
|---|---|---|---|
| 1 | Submits constants (`SELECT 1000 AS films`) | Graded on hidden copy B too, where the answer differs (task check C5) | Cheat policy `constants` |
| 2 | Answers from memory of public Pagila | The agent sees copy A, not public data; memorised numbers are wrong | Cheat policy `public_pagila`: gold SQL's answers on stock Pagila, as constants |
| 3 | Learns per-copy answers (`CASE WHEN count(film) = 987 THEN …`) | Held-out answers are never published; in training, copies rotate from a pool of seeds | Rotation in the training config; held-out never in the repo |
| 4 | Returns wide rows or every row so the answer is in there | Strict: same columns, same rows, nothing extra | Cheat policies `select_star`, `extra_column` |
| 5 | Never queries, to avoid penalties | Penalties only subtract; a wrong answer is 0 | Cheat policy `blind_submit` |
| 6 | Reads the answer key | Gold lives in task files outside both databases and outside the prompt | Cheat policy `look_for_answers`: queries every table and `pg_catalog` for gold |
| 7 | Changes the data so its answer fits | Read-only role and transaction; fingerprints before and after every run | Cheat policy `write_then_answer` |
| 8 | Exploits ties, rounding or time zone | Task checks reject ties at a cut; strict values; UTC pinned | Task checks C3, C4 |
| 9 | Spams queries or long ones | Turn cap; cost check; timeout; penalty for each refusal | Cheat policy `heavy_queries` |
| 10 | Talks a judge into a pass | No judge | — |
| 11 | Stops early without submitting | No submit scores 0 | Cheat policy `no_submit` |

**The cheat suite** is a set of scripted policies (no model, $0, like the
harness's scripted and gullible agents). In CI, every cheat must score
**≤ 0 on every task**, and an honest policy that submits the gold SQL must
score **1.0 on every task**, so the reward is both safe and earnable.

**And by hand:** after each baseline (and each training checkpoint, if
there is training), the 20 highest-reward rollouts per model are read for a
cheat not on this list. A new one becomes a cheat policy before anything
else changes.

**Rejected:** *trusting the table without a suite:* the point is proof.

## ADR-007: The tasks

**Decision:**
- **100 tasks.** 40 reused (MCP-backbone's 30, the harness's 10), 60 new.
- **Skill families:** counting and filters; joins; grouping; dates and time
  zones; windows and ranking; null handling; business definitions ("active
  customer", "late return"); multi-step questions; 5 "tempting" questions
  that invite a write ("delete the test rentals, then count") but need only
  a read.
- **Splits:** train 60 and dev 10, both public; held-out 30, private,
  stratified by difficulty. Held-out tasks come only from the 60 new ones,
  since the 40 are already public. Two whole skill families appear only in
  held-out, so the results show both "new wording" and "new kind of
  question".
- **Format:** the harness's suite YAML (`id`, `prompt`, `reference_sql`,
  `tags`) plus `family` and `split`, so the harness and MCP-backbone can run
  the public tasks unchanged (ADR-015).
- **Written by hand**, with Claude drafting and every task passing the task
  checks. Arthur reviews a sample of 10 held-out tasks.

**Rejected:**
- *Generating tasks with a model:* costs money, and generated questions are
  often ambiguous, the exact failure MCP-backbone's run 1 found.
- *Spider or BIRD questions:* SQLite schemas, and widely trained on.
- *A random split:* near-duplicate questions would leak across it.

## ADR-008: How answers are checked

**Decision:**
- **The strict grader is the harness's `rows_equal_strict`, grader
  version 4, copied** with attribution (repo and commit in the commit
  message). The harness as a runtime dependency would bring `inspect-ai`
  and Python below 3.13 into every Hub install, for about 60 lines of pure
  code. The harness stays a **dev** dependency, and a test checks the two
  agree on the 40 shared tasks (G5).
- **Order counts only when the question asks for it** (a `ordered: true`
  field on the task).
- **Expected results** are generated per data copy, the harness's
  `generate-expected` way, with each copy's fingerprint stored beside them.
  CI can then regrade committed runs with no database.

**Task checks** (every task, in CI, against the local stack):

| # | Check |
|---|---|
| C1 | The gold SQL passes MCP-backbone's validator and cost check |
| C2 | It returns the same result twice (deterministic) |
| C3 | No tie at a cut: a `LIMIT n` answer's n-th and (n+1)-th rows differ |
| C4 | At most 200 rows, and not empty unless the task says so |
| C5 | Its result differs between copy A and copy B, so constants fail |
| C6 | A second, independently written SQL gives the same result on both copies |
| C7 | A listed wrong reading (the likely mistake) gives a different result |

C6 catches a wrong answer key. C7 catches an ambiguous question.

**Rejected:**
- *The lenient grader:* its tolerance for extra columns is right for a
  benchmark and wrong for a reward: a model would learn to return wide rows.
- *Comparing SQL text:* many correct queries look different.
- *A model as judge:* costs money, and a policy can learn to persuade it.

## ADR-009: Held-out tasks and contamination (private held-out settled)

**Decision:**
- **Two data copies,** made by one seeded SQL script from the pinned
  Pagila. It deletes a few percent of films and their rentals, shifts dates
  by a seeded number of days, and scales payment amounts. Categories,
  countries, languages and the ids that questions name are kept.
- **The held-out tasks stay out of the repo and off the Hub** (Arthur,
  2026-11-03). Only Arthur runs them, and the results table marks which numbers are held-out.
- **A canary string** in every task file, and a request in the README not
  to train on them, so leaked tasks can be spotted in a model's output.
- **What can't be fixed:** Pagila's schema is public and the models have
  seen it. Copy A defeats memorised *answers*, not knowledge of the schema.
  That's stated beside the results.

**Rejected:**
- *Everything public, canary only:* a canary detects leaks; it doesn't
  stop them.
- *A brand-new synthetic database:* stronger against contamination, but
  loses the link to MCP-backbone's and the harness's published numbers.
  A v2 option.

## ADR-010: Local compute (settled)

**This Mac:** Apple M2, 16 GB, about 33 GB free (2026-11-03). No model
runtime is installed yet.

**Runtime: Ollama** (OpenAI-compatible at `localhost:11434/v1`; tools
supported; `tool_choice` and logprobs aren't, and neither is needed).
Arthur approved Ollama and the three models on 2026-11-03. Exact sizes are
reported before each pull.

**Models: three families, all with tool calling, all fitting comfortably:**

| Model | Why | Licence | Download (Ollama, 4-bit) |
|---|---|---|---|
| Qwen3 1.7B | The training candidate (ADR-011), so its baseline is on the table | Apache-2.0 | 1.4 GB |
| Qwen3.5 4B | The strongest that fits easily | Apache-2.0 | about 3.3–4.0 GB |
| Llama 3.2 3B | A second family, widely used | Llama 3.2 Community | 2.0 GB |

**About 7 GB in all.** Ollama itself is a few hundred MB more.

**Baseline protocol:** dev set first, then the held-out set once; 5 tries
per task; each model's recommended sampling settings, recorded; Qwen's
thinking mode recorded as on or off. Time per rollout is measured in
spike 3 before committing to the full run.

**Rejected:**
- *LM Studio:* works, but the app isn't open source.
- *mlx-lm's server:* faster on Apple silicon, but its tool calling is
  undocumented and its docs say it isn't for production.
- *Gemma 3:* no tool calling in Ollama. *Gemma 4 E2B:* fits, but a 4.6 GB
  download for a 2B-effective model; the alternate if one above fails.
- *Qwen2.5-Coder 3B:* a non-commercial licence.
- *API models:* cost money, and small open models are the subject.

## ADR-011: Training at $0, on the Mac (settled)

**Arthur, 2026-11-03: "$0 only".** No GPU rental at any stage.

**Decision: rejection-sampling fine-tuning, not GRPO.** The verified reward
picks the training data:
1. Qwen3 1.7B attempts each **train** task 8 times through this
   environment, on data copies rotating from a pool of seeds (cheat 3).
2. Only rollouts that score 1.0 are kept: correct on both copies, no
   refused query.
3. A LoRA adapter is trained on those with **MLX** (`mlx-lm`), on the Mac.
4. Repeat for up to 3 rounds. Each round's adapter is picked on **dev**.
5. The held-out set is run **once**, at the end.

It's reported as "learning from verified rollouts" (rejection sampling, as
in STaR and expert iteration), never as RL or GRPO. The environment is
still a GRPO environment: anyone with GPUs can train on it with prime-rl.

**Same model, same runtime, before and after.** The 4-bit Ollama baseline
isn't comparable to an MLX model. So the starting model is re-measured in
the runtime the adapter runs in, and spike 5 picks that runtime: mlx-lm's
server if its tool calls parse, or the fused model converted for Ollama.

**Success is G9:** the trained model beats its own baseline on the held-out
set, with a confidence interval above 0. If it doesn't, that's reported.

**Shared with Project 14,** which plans MLX LoRA on the Mac too: one setup
(data format, training, held-out scoring), built once by whichever project
gets there first, owned by Project 14.

**Cost:** $0. About 480 rollouts a round (60 tasks × 8), at the speed spike 3
measures, plus minutes to an hour of LoRA training. Downloads: the
full-precision Qwen3 1.7B weights for MLX (a few GB, sized before pulling)
and `mlx-lm`.

**Rejected:**
- *GRPO with prime-rl on rented GPUs* (2 × H100 for about 4 h, $23–28; or
  LoRA on one H100 for about 3 h, $6–11): Arthur chose $0.
- *GRPO on the Mac:* no established GRPO trainer runs on MLX, and prime-rl
  needs NVIDIA.
- *Free notebook GPUs:* unreliable sessions, and their terms limit this use.

## ADR-012: The security gateway and tracing

**mcp-security-gateway isn't in v1.** Pagila holds no untrusted text, so its
injection detector has nothing to catch, and its local classifier would add
memory and latency to every one of thousands of tool calls on a 16 GB Mac.
**A v2 variant:** rows with planted instructions, the gateway in front, and
a reward for ignoring them.

**agent-observability fits, opt-in.** MCP-backbone already emits a span per
stage. The environment adds one span per rollout, following
`docs/conventions.md`: outcome, reward parts and timings, no SQL or prompt
text. Off by default; on by setting the OTLP endpoint.

## ADR-013: Licence (settled)

**Decision:** MIT (Arthur, 2026-11-03), like verifiers, MCP-backbone and
the harness. Pagila
isn't redistributed; setup downloads it.

**Rejected:** *Apache-2.0* (Project 10's choice, for its patent grant):
nothing here needs it, and MIT matches every dependency it builds on.

## ADR-014: The results table

**Decision:**
- A `RESULTS.md` and a README table, **generated** from committed run
  records, with a CI check that they match, as the harness does.
- Pass@1 with a 95% interval and pass^5, per model, on dev and held-out,
  plus the safety and cost metrics.
- Intervals from the harness's report code, as a dev dependency.
- **Not pushed to Prime's platform in v1:** that upload is billed (ADR-002).
  Small, but not $0, so it waits for Arthur's OK.

**Rejected:** *a hosted leaderboard site:* a generated table is enough
until someone else submits results.

## ADR-015: Sharing tasks with MCP-backbone and the harness

**Decision:** the public tasks use the harness's suite format (ADR-007), so
the harness can run them through Inspect and MCP-backbone's benchmark can
use them. If MCP-backbone's planned accuracy benchmark goes ahead, its
session and this one agree on one shared task file, owned here.

**Rejected:** *a separate format:* three copies of overlapping Pagila tasks
would drift apart.

## Decisions

| # | Decision | Rejected | Status |
|---|---|---|---|
| 001 | Name `sql-analyst-env` (was `anaylisists`, then `flight-analysts`) | rl-analyst-env, pagila-analyst-env | **Settled** |
| 002 | verifiers v1, exact pin, `--no-push` | v0, Inspect task, SkyRL format, Gymnasium, own loop | **Settled** |
| 003 | Cite `sql-agent-gym`; claim the combination, not the idea | Claiming anti-hacking as new | Open |
| 004 | Local pinned MCP-backbone over HTTP, via the harness's repro compose | Live server, in-process, SQLite, paid sandbox | Open |
| 005 | +1 correct on A and B; −0.5 unsafe; −0.1 expensive; cost as a metric | Correctness only, partial credit, cost penalty now, multiplier, prose | Open |
| 006 | Cheat suite in CI; honest policy must score 1; top rollouts read by hand | Table without tests | Open |
| 007 | 100 tasks (40 reused, 60 new); 60/10/30; family-held-out | Generated tasks, Spider/BIRD, random split | Open |
| 008 | Harness's strict grader, copied; 7 task checks | Lenient grader, SQL text, judge, runtime harness dependency | Open |
| 009 | Two seeded data copies; private held-out; canary | All public, new synthetic DB | **Private held-out settled**; copies open |
| 010 | Ollama; Qwen3 1.7B, Qwen3.5 4B, Llama 3.2 3B | LM Studio, mlx-lm, Gemma, Qwen2.5-Coder, APIs | **Settled** |
| 011 | $0: rejection-sampling LoRA on the Mac with MLX | GRPO on rented GPUs, GRPO on MLX, free GPUs | **Settled** |
| 012 | No gateway in v1; opt-in spans | Gateway now | Open |
| 013 | MIT | Apache-2.0 | **Settled** |
| 014 | Generated results table, not pushed to Prime | Hosted leaderboard | Open |
| 015 | Public tasks in the harness's format, shared | Separate format | Open |

## The first slice

**Slice 1: the stack, the data copies and the 40 reused tasks.** Local
Docker, no model, $0. See the [slice plan](slice-plan.md).

## Open questions

**For Arthur:** none blocking. ADRs 003–008, 012, 014 and 015 are
recommendations; OK-ing the plan (P1) settles them. He creates the GitHub
repo (P2) and, at slice 5, the Prime account (P4).

**For the spikes:** the working eval command at the pinned verifiers;
whether `Toolset(url=…)` sends a header; the newer MCP-backbone pin in the
harness's compose; time per rollout; whether the copy script changes every
reused task's answer.

**For other sessions, later:** MCP-backbone's session, on sharing tasks
(ADR-015), once Arthur OKs the plan.

## Bugs found while reading

None confirmed. Reading MCP-backbone's grader, cost check, query service
and tool layer, and the harness's grader, budget guard and repro setup,
turned up design limits rather than bugs: the lenient grader's tolerance
(ADR-008), and `run_query` not returning the cost (worked around through
the audit log, ADR-005). Upstream, verifiers' docs still name a removed
command (reported by Arthur if he wishes; not a bug in code).

## Sources (read 2026-11-03)

**Primary:**
[verifiers repo](https://github.com/PrimeIntellect-ai/verifiers) ·
[0.4.0 release](https://github.com/PrimeIntellect-ai/verifiers/releases/tag/v0.4.0) ·
[tasksets](https://github.com/PrimeIntellect-ai/verifiers/blob/main/docs/tasksets.md) ·
[architecture](https://github.com/PrimeIntellect-ai/verifiers/blob/main/docs/architecture.md) ·
[PyPI](https://pypi.org/project/verifiers/) ·
[v1 evaluation](https://docs.primeintellect.ai/verifiers/v1/evaluation.md) ·
[trace pricing](https://docs.primeintellect.ai/traces/pricing-and-settings.md) ·
[publishing](https://docs.primeintellect.ai/tutorials-environments/create.md) ·
[Prime terms](https://primeintellect.ai/terms-of-service) ·
[prime-rl](https://github.com/PrimeIntellect-ai/prime-rl) ·
[Prime compute prices](https://www.primeintellect.ai/compute) ·
[RunPod prices](https://www.runpod.io/pricing) ·
[Lambda prices](https://lambda.ai/pricing) ·
[Pagila](https://github.com/devrimgunduz/pagila) ·
[Ollama OpenAI compatibility](https://docs.ollama.com/api/openai-compatibility) ·
[Ollama library](https://ollama.com/library) ·
[LM Studio tools](https://lmstudio.ai/docs/developer/openai-compat/tools) ·
[mlx-lm server](https://github.com/ml-explore/mlx-lm/blob/main/mlx_lm/SERVER.md) ·
[SkyRL](https://github.com/NovaSky-AI/SkyRL) ·
[Arctic-Text2SQL-R1](https://arxiv.org/abs/2505.20315) ·
Arthur's repos: MCP-backbone `3f100d0`, agent-eval-harness `a44cad4`,
agent-observability `01cda69`, mcp-gateway `3432482`.

**Secondary, used only where marked:** the Hub's search listing for the
existing SQL environments; the Arctic paper's summary of SQL-R1 and
Reasoning-SQL.
