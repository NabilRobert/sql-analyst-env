"""An RL training environment for a data-analyst agent: business questions
over Postgres, answered through MCP-backbone's tools, graded by code.

verifiers finds the environment by this package's name and loads the one
Taskset exported here."""

from analyst_env.environment import AnalystTaskset

__all__ = ["AnalystTaskset"]
