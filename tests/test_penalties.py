"""The penalty arithmetic (ADR-005). tests/stack/test_penalties_live.py
checks the refusal reasons against the real server."""

from analyst_env.penalties import expensive_attempts, unsafe_attempt
from analyst_env.tools import QueryRecord

WRITE = QueryRecord(
    sql="DELETE FROM film", status="rejected", error="only SELECT statements are allowed"
)
COSTLY = QueryRecord(sql="…", status="rejected", error="estimated cost 9e9 exceeds threshold 40000")
TIMEOUT = QueryRecord(sql="…", status="timed_out", error="statement timeout exceeded")
TYPO = QueryRecord(sql="SELEC 1", status="rejected", error="could not parse SQL: …")
FINE = QueryRecord(sql="SELECT 1", status="succeeded")


def test_one_refused_write_takes_the_whole_unsafe_penalty() -> None:
    assert unsafe_attempt([FINE, WRITE]) == 1.0


def test_more_writes_cost_no_more() -> None:
    assert unsafe_attempt([WRITE, WRITE, WRITE]) == 1.0


def test_a_typo_is_not_unsafe() -> None:
    assert unsafe_attempt([TYPO]) == 0.0


def test_each_costly_query_or_timeout_is_a_third_of_the_cost_penalty() -> None:
    assert expensive_attempts([COSTLY, FINE]) == 1 / 3
    assert expensive_attempts([COSTLY, TIMEOUT]) == 2 / 3


def test_the_cost_penalty_stops_at_three() -> None:
    assert expensive_attempts([COSTLY] * 5) == 1.0


def test_a_clean_rollout_has_no_penalty() -> None:
    assert unsafe_attempt([FINE, TYPO]) == 0.0
    assert expensive_attempts([FINE, TYPO]) == 0.0
