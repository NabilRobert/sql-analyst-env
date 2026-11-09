# Journey log

What happened building this: what was tried, what broke, and why the
decisions landed where they did. Git history has the what; this has the
why and the dead ends. Every number here comes from a file in the repo
(named in brackets) or from a run record under `runs/`.

## 2026-11-03: the plan, and an API that had just vanished

The idea: an RL environment where a model answers analyst questions over a
real Postgres database, through the same MCP server (MCP-backbone) a person
would use, graded so that it can't be gamed.

- **verifiers 0.4.0 had removed its whole v0 API three weeks earlier**
  (`SingleTurnEnv`, `ToolEnv`, `Rubric`). The docs and most examples still
  used it. So the environment is written against v1, and the version is
  pinned exactly (ADR-002).
- **The defaults cost money.** v1's eval uploads traces to Prime Intellect
  (billed per GiB), and its default agent runtime and model client are
  paid services too. Every run here passes `--no-push`, and a test proves
  it: an egress guard catches the upload when it's switched back on, and
  sees nothing when it's off [tests/stack/test_no_upload.py].
- **Reuse over rebuilding.** The stack is agent-eval-harness's repro image,
  fetched by git at a pinned commit; the 40 starting tasks are the
  harness's, in its format. That gave a check for free: our grader must
  agree with the harness's committed verdicts, and it does on all 212
  [tests/test_harness_agreement.py].

## Slice 1: two copies of the data

A pasted answer is the easiest cheat. So the grader never compares values:
the model submits SQL, and the grader runs it on copy A (the one the model
explored) and copy B (one it never saw, with shuffled answers). A number
copied from A fails on B. Each copy's data has a stored fingerprint, and
checks refuse to run if it changes [analyst_env/fingerprint.py].

## Slice 2: the reward, and cheats written before the model

Before any model ran, scripted policies played every task through the real
`vf-eval`: two honest ones that must score 1.0 everywhere, nine cheats
that must each score exactly what their defence allows, never above 0,
and one more that writes beside a right answer and must score exactly
0.5 [tests/scripted/policies.py, tests/stack/test_cheat_suite.py].
Writing the cheats first is what made the reward trustworthy: each
defence is pinned by a test before a model could find the gap.

verifiers traps found on the way (upstream, worked around): a stop hook
with a parametrised annotation raises `TypeError`; sync rewards fail with
an asyncio error although the docs show sync signatures.

## Slice 3: 60 new tasks, 30 of them held out

The held-out 30 live outside the repo, and a test fails if any of their
text appears in it. One full run was thrown away: a held-out answer key
turned out to be, word for word, the wrong reading of a public task, and I
edited it mid-run. The task was rewritten and the run redone from the
start, so every number comes from one clean run.

## Slice 4: baselines, and pass rules fixed first

Before any model ran, the pass rules were written down: what makes a run
count, and that held-out runs once per model, never rerun to change a
number. Four amendments followed, each made before the runs it affected,
each with the reason:

1. One rollout at a time (the Mac is shared).
2. The first qwen3 dev run was voided: one reply looped for 163,840 tokens
   over 2.5 hours, because Ollama shifts its context window and carries on
   instead of stopping. Fix: a reply cap of 4,096 tokens.
3. The second was voided too: one call reached 14,769 tokens, 23 over the
   90% line. Fix: a 24,576-token context.
4. The stack died after the last held-out try of one model but before the
   after-run fingerprint check. Rather than show the held-out tasks to the
   model a second time, the check was done late, and the record built from
   the finished traces (`analyst-env record`).

Then the held-out runs went wrong in two new ways:

- **The disk filled mid-run.** qwen3.5's first held-out attempt got 28
  good tries, then Docker stopped answering and 54 tries errored. No record
  was written, so this was the one restart the rules allow for an
  infrastructure crash. The rerun had a disk watcher that would stop it
  cleanly at 300 MB free.
- **A rule broke in a way nobody could have caught before the run.** Seven
  of qwen3.5's held-out tries had a call over 22,118 tokens, the rule-2
  line; the longest was 56,184, more than twice the window. Ollama runs
  qwen3.5 on its MLX runner, which ignores `OLLAMA_CONTEXT_LENGTH` while
  still reporting it. So nothing was cut off: those tries saw more context
  than the rule allows. Held-out can't be rerun, so the choice was to void
  the number or count it with the breach stated. Arthur chose to count it;
  RESULTS.md lists the seven tries and the score with the one right one
  counted as wrong (93 of 150 instead of 94).

Results [RESULTS.md]:

| Model | Dev pass@1 | Held-out pass@1 | Held-out pass^5 |
|---|---|---|---|
| Qwen3.5 4B | 74.0% | 62.7% | 14/30 |
| Qwen3 1.7B | 2.0% | 0.0% | 0/30 |
| Llama 3.2 3B | 0.0% | 0.0% | 0/30 |

What the hand review found [docs/rollout-review.md]: no cheats. The small
models fail on format, not reasoning: qwen3 runs the right query, then
types the answer instead of calling `submit_answer`; llama guesses table
names and writes tool calls as text. Three grading gaps came out of it:
time zones, hard-coded keys, and a wrong SQL dialect (a MySQL
`DATE_FORMAT`) costing the same −0.5 as a dangerous function.

## Slice 5: a clean machine, and a race

- **Main's CI went red on one task, x04, three runs out of three.** The
  CI logs need a GitHub sign-in, so the test now writes its failures as
  annotations anyone can read. They showed the cause: stock Pagila was
  never analyzed on CI's fresh database, so the cost check estimated
  x04's answer key at 177,714 against a 40,000 limit and refused it. The
  test then kept the empty result as the answer, and the scripted model
  server crashed on it without replying. A local stack that had run for
  days had real statistics and never failed. Setup now runs ANALYZE, and a
  failed answer key stops the test with its reason.
- **The clean-machine check (G6) failed on a fresh clone: 14 failed and
  83 errored.** MCP-backbone makes a workspace's rate-limit counter on
  first use, and two concurrent first queries made two counters; after
  that every query in that workspace failed with "try again in a moment",
  for good. It hit copy_b, the grader's copy. Reported with a repro, and
  fixed upstream, where the same race turned up in the schema cache.
  Until the pin includes the fix, setup makes those rows itself before
  the server starts. On the next clean run: 188 passed, 6 skipped.

## Bugs found in the code this builds on

- **MCP-backbone** refused top-level UNION, INTERSECT and EXCEPT with the
  reason a DELETE gets, so a read-only query took the unsafe penalty. It
  was already fixed upstream; the pin moved after slice 4 so all baselines
  ran on one server (`dd98f06`). The move could lower some unsafe counts,
  but no pass@1 [docs/rollout-review.md, "Upstream"].
- **MCP-backbone** broke a workspace for good on two concurrent first
  uses (above). Fixed upstream on `fix/concurrent-first-use`.
- **Ollama** keeps generating past its context window by shifting it,
  which turned one reply into 2.5 hours (amendment 2), and its MLX runner
  ignores the context setting it reports (the held-out breach above).
- **verifiers** counts cached prompt tokens apart from prompt tokens, so
  the longest-call check undercounted until it added them.

## What I'd do next

- Training (cut for the deadline): rejection-sampling LoRA on the Mac. With
  base scores near zero for the small models, it would have had almost
  nothing to train on; a stronger base model is the first step.
- Close the grading gaps: grade copy B under a non-UTC time zone, shuffle
  lookup keys in copy B, and stop counting an unknown function as unsafe.
- Move the pin past MCP-backbone's first-use fix and drop the setup
  workaround.
- The Environments Hub listing (G7) was skipped by choice; the repo is the
  public piece.
