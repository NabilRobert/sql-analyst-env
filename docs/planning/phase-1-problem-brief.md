# Phase 1: Problem Brief

**Project:** a reinforcement-learning (RL) training environment for a
data-analyst agent. The agent gets a business question, explores a real
Postgres database through Arthur's read-only MCP-backbone server, writes
SQL and submits an answer. Code checks the answer and scores it. It is the
thirteenth portfolio piece.

The repo and Hub name is `flight-analysts` (Arthur, 2026-11-03; see ADR-001).
It isn't Project 10, AI Flight School, and it uses no flight data.

## Problem

**For RL practitioners:**
- **RL with verifiable rewards is a main post-training method,** and the
  environments are the bottleneck. A model learns whatever the reward pays
  for, so a weak checker trains a cheater.
- **Most public environments are toys.** Single-turn, a string compare at
  the end, no tools, no cost, no safety. A real analyst works in turns:
  look at the schema, try a query, fix it, answer.
- **Existing text-to-SQL RL setups mostly run on SQLite** and reward one
  execution match (Phase 5, ADR-003). One Hub environment,
  `sql-agent-gym`, already targets reward hacking. None found runs the
  agent through a production-style server with a validator, a cost check
  and an audit log, or pays for safe and cheap queries. All of them use
  verifiers' old API, which 0.4.0 removed.

*To verify in slice 4, not assumed:* that small open models score low
enough on the held-out tasks for training to have room to show a gain.

**For the portfolio:**
- Every earlier project tests, guards or traces agents. None trains one.
- A reviewer can't yet see reward design: how a reward gets gamed, and
  proof that the known tricks score zero.
- MCP-backbone is measured as a tool for a frontier model. This shows the
  same server as a training ground for small open models.

## Users

| Party | Who | Wants |
|---|---|---|
| **RL practitioners** | People who pull environments from Prime Intellect's Environments Hub | An environment that installs in one step, runs locally, and can't be gamed |
| **Arthur (builder)** | Runs the baselines and, if approved, one training run | A piece that shows post-training skills, at $0 for v1 |
| **Reviewer / hiring team** | AI labs and AI-tooling teams | Reward design, hacking defences, held-out discipline, honest limits |

## Positioning: what makes this one different

The idea (text-to-SQL RL) is not new, so the idea isn't what's being shown.
What is:

1. **Real tools, real guards.** The agent uses MCP-backbone's four tools
   over Postgres, with the same validator, cost check, read-only role and
   audit log the live server has. It works in several turns.
2. **A reward that resists gaming, with proof.** Not a new idea (ADR-003),
   so the proof is the contribution. The submitted SQL is run on
   the database the agent saw *and* on hidden copies with different data,
   so a query that hard-codes the answer fails. A suite of scripted cheats
   must score 0 on every task, in CI.
3. **Held-out discipline.** A private held-out set, a canary string, and
   data the models can't have memorised: the agent queries a perturbed
   Pagila, not the public one.
4. **$0 and reproducible.** Pinned images, a data fingerprint, and baselines
   from three small models running on a 16 GB Mac.

## Goals and how they're measured

| # | Goal | Target | Measured by |
|---|---|---|---|
| G1 | Known cheats earn nothing | Every scripted cheat (ADR-006) scores **0** on every task | Hacking suite in CI |
| G2 | Every answer key is sound | All 100 tasks pass the task checks (ADR-008): runs, deterministic, no ties at a cut, differs between data copies, a wrong reading fails | Task-check test in CI |
| G3 | 100 tasks | 70 public (train and dev), 30 held out | Task files |
| G4 | Honest baselines | 3 local models on the held-out set, 5 tries each, with confidence intervals | Committed run records |
| G5 | The grader agrees with Arthur's earlier ones | On the 40 tasks shared with agent-eval-harness, same verdicts as its strict grader | Regrade test |
| G6 | Anyone can run it | `uv` install plus one `docker compose up`; no key or GPU | A clean-machine run |
| G7 | It's public | Published on the Environments Hub, with a results table | The Hub page |
| G8 | It costs nothing | $0 spent, every slice | No paid service used |
| G9 | Training helps, at $0 | Qwen3 1.7B, LoRA-trained on its own verified rollouts on the Mac, beats its own baseline on the held-out set, interval above 0 | A training record |

## Non-goals (v1)

- **Paid training.** No rented GPUs at any stage (Arthur, 2026-11-03).
  Slice 7 trains on the Mac at $0, by rejection sampling, not GRPO
  (ADR-011).
- **A model as judge.** Every reward is computed by code.
- **Write access.** The agent never changes data, in any version.
- **Rollouts against the live server.** Its limits (5 queries per hour per
  workspace) and the small shared server rule it out. Everything runs
  locally.
- **Other databases.** Pagila only; a second database is a v2 question.
- **The security gateway in the loop.** A v2 variant at most (ADR-012).

## Decisions (settled with Arthur)

All on 2026-11-03:
1. **Name:** `flight-analysts` (first recorded as `anaylisists`).
2. **Framework:** verifiers v1, published publicly on the Environments Hub
   from Arthur's account, MIT licence.
3. **Local models:** Ollama with Qwen3 1.7B, Qwen3.5 4B and Llama 3.2 3B
   (about 7 GB of downloads approved).
4. **Held-out tasks:** private, never in the repo or on the Hub.
5. **Money:** $0 only. Training, if it happens, runs on the Mac.

Everything else in Phase 5 is a recommendation until Arthur agrees.

## Open questions

See the end of [Phase 5](phase-5-architecture-decisions.md#open-questions).

## Cost of doing nothing

Nothing breaks. The portfolio keeps showing evaluation without training,
and MCP-backbone's tasks stay a benchmark rather than a training ground.
