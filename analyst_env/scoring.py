"""Is the submitted query right? Its result must strictly equal the answer
key's on copy A, which the agent saw, and on copy B, which it never saw
(ADR-005, ADR-009). A query that hard-codes copy A's answer fails on B.

Both queries run through MCP-backbone at grading time, so the submission
meets the same validator and cost check the agent did."""

import functools

from analyst_env.backbone import BackboneCopy, mcp_url, open_copies, read_stack_keys
from analyst_env.grading import results_match


class AnswerKeyBroken(RuntimeError):
    """The answer key itself failed: the rollout can't be scored, so it's
    marked errored rather than given a reward (verifiers' own advice)."""


@functools.cache
def _stack_keys() -> dict[str, str]:
    return read_stack_keys()


async def is_correct(submitted_sql: str, reference_sql: str, is_ordered: bool) -> bool:
    async with open_copies(mcp_url(), _stack_keys()) as copies:
        for copy in copies:
            if not await _matches_on(copy, submitted_sql, reference_sql, is_ordered):
                return False
    return True


async def _matches_on(
    copy: BackboneCopy, submitted_sql: str, reference_sql: str, is_ordered: bool
) -> bool:
    expected = await copy.run_query(reference_sql)
    if not expected.is_success or expected.truncated:
        raise AnswerKeyBroken(
            f"the answer key failed on {copy.name} ({expected.status}: {expected.error}): "
            "run `uv run pytest tests/stack` to find the broken task"
        )
    actual = await copy.run_query(submitted_sql)
    # A cut-off result has rows the agent never saw, so it isn't an answer.
    if not actual.is_success or actual.truncated:
        return False
    return results_match(actual.rows, expected.rows, is_ordered)
