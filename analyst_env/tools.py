"""The agent's tools: MCP-backbone's four, on copy A, plus `submit_answer`.

A verifiers Toolset is an MCP server of our own that the agent's harness
calls. Each tool forwards to the local MCP-backbone with copy A's key, so
the key never reaches the model (requirement E2), and records what
happened in the rollout's state, which the rewards read afterwards.

One server is shared by every rollout of a run (`AnalystTaskset.toolsets`);
verifiers routes each call's state to the right rollout. Run on its own
(`python -m analyst_env.tools`) when verifiers launches it."""

from typing import Any

import verifiers.v1 as vf  # pyright: ignore[reportMissingTypeStubs]
from pydantic import BaseModel

from analyst_env.backbone import BackboneCopy, connect, mcp_url, read_stack_keys

AGENT_COPY = "copy_a"
ANSWER_RECORDED = "Answer recorded. You're done: reply with a one-line summary."
ALREADY_SUBMITTED = "An answer was already submitted; only the first one counts."


class QueryRecord(BaseModel):
    """One query the agent ran (or submitted), as MCP-backbone answered."""

    sql: str
    status: str
    error: str | None = None


class RolloutState(vf.State):
    queries: list[QueryRecord] = []
    submitted_sql: str | None = None


class AnalystToolsConfig(vf.SharedToolsetConfig):
    """Runs as a local subprocess (verifiers' default for a shared server)."""


class AnalystTools(vf.Toolset[AnalystToolsConfig, RolloutState]):
    # Advertise the tools by their own names, not `analyst_tools_run_query`.
    TOOL_PREFIX = None

    _copy: BackboneCopy

    async def setup(self) -> None:
        keys = read_stack_keys()
        context = connect(AGENT_COPY, mcp_url(), keys[AGENT_COPY])
        self._copy = await self._exit_stack.enter_async_context(context)

    async def _query(self, sql: str) -> dict[str, Any]:
        response: dict[str, Any] = await self._copy.call_tool("run_query", {"sql": sql})
        status = str(response.get("status", "errored"))
        record = QueryRecord(sql=sql, status=status, error=response.get("error"))
        self.state.queries.append(record)
        return response

    @vf.tool
    async def list_tables(self) -> Any:
        """List the tables in the database."""
        return await self._copy.call_tool("list_tables", {})

    @vf.tool
    async def describe_table(self, table_name: str) -> Any:
        """Show a table's columns and their types."""
        return await self._copy.call_tool("describe_table", {"table_name": table_name})

    @vf.tool
    async def sample_rows(self, table_name: str, limit: int) -> Any:
        """Show a few example rows from a table. `limit` is 1 to 100; 10 is usually enough."""
        arguments = {"table_name": table_name, "limit": limit}
        return await self._copy.call_tool("sample_rows", arguments)

    @vf.tool
    async def run_query(self, sql: str) -> Any:
        """Run one read-only SQL SELECT and see its result (at most 200 rows)."""
        return await self._query(sql)

    @vf.tool
    async def submit_answer(self, sql: str) -> str:
        """Submit your final answer: the one SQL query whose result answers the
        question. Only the first submission counts."""
        if self.state.submitted_sql is not None:
            return ALREADY_SUBMITTED
        self.state.submitted_sql = sql
        # Run it once like any query, so a write submitted as the answer
        # still counts as an unsafe attempt.
        await self._query(sql)
        return ANSWER_RECORDED


if __name__ == "__main__":
    AnalystTools.run()
