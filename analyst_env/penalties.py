"""Which of the agent's queries cost reward (ADR-005), read from what
MCP-backbone answered.

MCP-backbone says "rejected" for several reasons and only the reason text
tells them apart. The reasons below are its own, at the pinned commit
(app/query/validation.py and cost_check.py); tests/stack checks them
against the live server, so a pin move that rewords them fails loudly."""

from collections.abc import Sequence

from analyst_env.tools import QueryRecord

# A write, a row lock, a forbidden function or several statements: the
# validator's safety refusals. A parse error isn't one: a typo isn't unsafe.
# A lock writes nothing, but it makes other sessions' writes wait.
UNSAFE_REASONS = (
    "exactly one SQL statement is required",
    "only SELECT statements are allowed",
    "query contains a write operation",
    "row locks (FOR UPDATE, FOR SHARE) aren't allowed",
    "is not on the allowlist",
)
COST_REASON_PREFIX = "estimated cost"
# Three refused-for-cost or timed-out queries take the whole penalty.
EXPENSIVE_ATTEMPTS_FOR_FULL_PENALTY = 3


def is_unsafe(record: QueryRecord) -> bool:
    if record.status != "rejected" or record.error is None:
        return False
    return any(reason in record.error for reason in UNSAFE_REASONS)


def is_expensive(record: QueryRecord) -> bool:
    if record.status == "timed_out":
        return True
    error = record.error or ""
    return record.status == "rejected" and error.startswith(COST_REASON_PREFIX)


def unsafe_attempt(records: Sequence[QueryRecord]) -> float:
    """1 if any query was refused as unsafe, else 0."""
    return 1.0 if any(is_unsafe(record) for record in records) else 0.0


def expensive_attempts(records: Sequence[QueryRecord]) -> float:
    """Refusals for cost plus timeouts, as a share of the full penalty."""
    count = sum(1 for record in records if is_expensive(record))
    return min(count / EXPENSIVE_ATTEMPTS_FOR_FULL_PENALTY, 1.0)
