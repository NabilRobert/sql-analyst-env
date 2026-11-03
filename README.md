# A data-analyst RL environment

A reinforcement-learning environment for a data-analyst agent. The agent
gets a business question, explores a Postgres database through
[MCP-backbone](https://github.com/NabilRobert/MCP-backbone)'s read-only
tools, writes SQL and submits it. Code grades the answer: it must be right
on the database the agent saw **and** on a hidden copy with different data,
so a query that hard-codes the answer fails.

**Status: slice 1 of 7.** The local stack, the two data copies, the 40
reused tasks and the answer-key checks are built. The environment itself
(on Prime Intellect's `verifiers`), the reward and the cheat suite come in
slice 2. The plan is on the `docs/planning` branch.

## Run it

Needs Docker and [uv](https://docs.astral.sh/uv/).

```bash
docker compose up -d --wait   # MCP-backbone + Postgres + two copies of Pagila, localhost only
uv run pytest                 # every task's answer key, checked through MCP-backbone
```

The first `up` builds the image and downloads Pagila (about 1 GB of
images on disk, 13 MB of data). `docker compose down -v` resets everything.

## Layout

```
compose.yaml          the local stack: Postgres, a one-shot setup, MCP-backbone
stack/
  setup_stack.py      loads Pagila, makes the copies, seeds one workspace per copy
  make_copies.sql     the seeded changes that turn Pagila into copy A or copy B
  fingerprints.json   each copy's data fingerprint; checks refuse other data
tasks/
  public.yaml         the public tasks (train and dev), with answer keys
  private/            held-out tasks; git ignores it
analyst_env/
  tasks.py            the task file's shape
  backbone.py         the client for the local MCP-backbone
  task_checks.py      the seven answer-key checks
  sql_variants.py     the rewrite behind the tie check
  grading.py          when two results are the same answer
  fingerprint.py      the data fingerprint
  cli.py              `uv run analyst-env fingerprint`
tests/                unit tests; tests/stack/ needs the stack running
docs/guide.md         how it works, in plain English
```

## Reused, not rebuilt

- **MCP-backbone** (MIT): the tools, validator, cost check, read-only role
  and audit log, at a pinned commit.
- **agent-eval-harness** (MIT): the image that builds MCP-backbone at a pin
  (fetched by git, not copied), the 40 Pagila tasks, the strict grader and
  the fingerprint queries.
- **Pagila** (PostgreSQL License): downloaded at a pinned commit during
  setup, not redistributed.

## Licence

MIT.
