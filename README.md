# Flight Analysts: a data-analyst RL environment

Despite the name, there's no flight data here: the database is Pagila, a
sample DVD-rental store. (Not to be confused with AI Flight School, a
separate project that's a flight simulator for AI agents.)

A reinforcement-learning environment for a data-analyst agent. The agent
gets a business question, explores a Postgres database through
[MCP-backbone](https://github.com/NabilRobert/MCP-backbone)'s read-only
tools, writes SQL and submits it. Code grades the answer: it must be right
on the database the agent saw **and** on a hidden copy with different data,
so a query that hard-codes the answer fails.

**Status: slice 4 of 7.** The local stack, the two data copies, the 40
reused tasks and their answer-key checks (slice 1); the environment on
Prime Intellect's [`verifiers`](https://github.com/PrimeIntellect-ai/verifiers)
v1, the reward, and a cheat suite of scripted policies that must fail to
game it (slice 2); 60 new tasks, the train, dev and held-out splits, and a
check that our grader agrees with agent-eval-harness's (slice 3);
baselines for three small local models, in [RESULTS.md](RESULTS.md)
(slice 4). The plan is on the `docs/planning` branch.

**Please don't train on the tasks.** Each task file carries a canary GUID
so leaked tasks can be spotted. The 30 held-out tasks aren't published.

## Run it

Needs Docker and [uv](https://docs.astral.sh/uv/).

```bash
docker compose up -d --wait   # MCP-backbone + Postgres + two copies of Pagila, localhost only
uv run pytest                 # answer keys, rewards and the cheat suite, against the stack
```

The first `up` builds the image and downloads Pagila (about 1 GB of
images on disk, 13 MB of data). `docker compose down -v` resets everything.
The full suite takes several minutes: the cheat suite plays about 840
rollouts through verifiers, with a scripted stand-in for the model.

Every evaluation goes through `analyst_env/run_eval.py`, which switches
off verifiers' paid defaults (uploads, hosted sandboxes, hosted models).

To run a baseline, with [Ollama](https://ollama.com) installed and the
model pulled:

```bash
OLLAMA_CONTEXT_LENGTH=24576 OLLAMA_NUM_PARALLEL=1 ollama serve
uv run analyst-env baseline qwen3:1.7b dev   # writes runs/dev/qwen3-1.7b.json
uv run analyst-env results                   # regenerates RESULTS.md
```

## Layout

```
compose.yaml          the local stack: Postgres, a one-shot setup, MCP-backbone
stack/
  setup_stack.py      loads Pagila, makes the copies, seeds one workspace per copy
  make_copies.sql     the seeded changes that turn Pagila into copy A or copy B
  fingerprints.json   each copy's data fingerprint; checks refuse other data
tasks/
  public.yaml         the 70 public tasks (train and dev), with answer keys;
                      the 30 held-out ones are never in the repo
analyst_env/
  environment.py      the verifiers Taskset and Task, with the rewards
  tools.py            the agent's tools: MCP-backbone's four plus submit_answer
  scoring.py          is the submitted query right on both copies?
  penalties.py        which refused queries cost reward
  run_eval.py         runs `vf-eval` locally, at $0
  baselines.py        the three baseline models, their settings, one run
  run_record.py       what a run leaves in runs/: numbers, no task text
  results.py          RESULTS.md from the run records
  tasks.py            the task file's shape, and where the held-out file is
  backbone.py         the client for the local MCP-backbone
  task_checks.py      the seven answer-key checks
  sql_variants.py     the rewrite behind the tie check
  grading.py          when two results are the same answer
  fingerprint.py      the data fingerprint
  cli.py              `uv run analyst-env fingerprint`
tests/                unit tests; tests/stack/ needs the stack running
  scripted/           scripted policies, a stand-in model server, an egress guard
  fixtures/           the harness's recorded verdicts, for the grader agreement test
runs/                 one run record per model and split
RESULTS.md            generated from runs/
docs/guide.md         how it works, in plain English
docs/rollout-review.md  the top-scoring tries, read by hand for new cheats
```

## Reused, not rebuilt

- **MCP-backbone** (MIT): the tools, validator, cost check, read-only role
  and audit log, at a pinned commit.
- **agent-eval-harness** (MIT): the image that builds MCP-backbone at a pin
  (fetched by git, not copied), the 40 Pagila tasks, the strict grader and
  the fingerprint queries.
- **verifiers** (MIT), pinned at 0.4.0: the rollout loop, the chat
  harness, the reward plumbing and the trace format.
- **Pagila** (PostgreSQL License): downloaded at a pinned commit during
  setup, not redistributed.

## Prior work

Text-to-SQL RL environments already exist, including one on the
Environments Hub focused on reward hacking (`vedant/sql-agent-gym`).
What's different here is the combination: Postgres behind a
production-style MCP server with a validator, a cost check and an audit
log; safety and cost penalties on top of the result match; and a hidden
second data copy, so memorised or hard-coded answers fail.

## Licence

MIT.
