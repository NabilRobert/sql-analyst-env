"""The penalties read MCP-backbone's refusal reasons as text
(analyst_env/penalties.py), so these check the live server still words
them the way the code expects: a pin move that rewords one fails here."""

import asyncio

import pytest

from analyst_env.backbone import connect, mcp_url
from analyst_env.penalties import is_expensive, is_unsafe
from analyst_env.tools import QueryRecord
from tests.scripted.policies import HEAVY_SQL

pytestmark = pytest.mark.stack


def _record(stack_keys: dict[str, str], sql: str) -> QueryRecord:
    async def run() -> QueryRecord:
        async with connect("copy_a", mcp_url(), stack_keys["copy_a"]) as copy:
            result = await copy.run_query(sql)
            return QueryRecord(sql=sql, status=result.status, error=result.error)

    return asyncio.run(run())


@pytest.mark.parametrize(
    "sql",
    [
        "DELETE FROM film",
        "SELECT 1; SELECT 2",
        "WITH gone AS (DELETE FROM film RETURNING 1) SELECT count(*) FROM gone",
        "SELECT pg_read_file('/etc/passwd')",
        "SELECT * FROM film FOR UPDATE",
    ],
)
def test_a_refused_unsafe_query_is_unsafe(stack_keys: dict[str, str], sql: str) -> None:
    record = _record(stack_keys, sql)
    assert record.status == "rejected"
    assert is_unsafe(record)
    assert not is_expensive(record)


def test_a_query_over_the_cost_limit_is_expensive(stack_keys: dict[str, str]) -> None:
    record = _record(stack_keys, HEAVY_SQL)
    assert is_expensive(record)
    assert not is_unsafe(record)


@pytest.mark.parametrize("sql", ["SELEC count(*) FROM film", "SELECT * FROM no_such_table"])
def test_a_mistake_is_neither_unsafe_nor_expensive(stack_keys: dict[str, str], sql: str) -> None:
    record = _record(stack_keys, sql)
    assert record.status != "succeeded"
    assert not is_unsafe(record)
    assert not is_expensive(record)


@pytest.mark.parametrize("operator", ["UNION", "INTERSECT", "EXCEPT"])
def test_a_top_level_set_operation_is_answered(stack_keys: dict[str, str], operator: str) -> None:
    """The pin before MCP-backbone PR #19 refused these with a write's
    reason, so a read-only query took the unsafe penalty."""
    sql = f"SELECT film_id FROM film {operator} SELECT film_id FROM inventory"
    assert _record(stack_keys, sql).status == "succeeded"
