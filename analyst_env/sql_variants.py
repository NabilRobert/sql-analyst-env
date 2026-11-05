"""Rewrites a gold query to expose a tie at a cut (task check C3).

"Top 3 films" is ambiguous if the 3rd and 4th films tie: the database may
return either, and an agent's correct query could lose to luck. To find
out, the query's ORDER BY gets every output column appended as a final
tie-breaker, once ascending and once descending. If the cut is clean, the
extra keys can't change which rows survive the LIMIT, so both versions
return the same rows. If they differ, the answer key depends on luck."""

import sqlglot
from sqlglot import expressions as exp

DIALECT = "postgres"


def tie_break_variants(sql: str) -> tuple[str, str] | None:
    """The two re-sorted versions of `sql`, or None if its outermost query
    has no LIMIT after an ORDER BY (nothing is cut, so nothing can tie)."""
    query = sqlglot.parse_one(sql, dialect=DIALECT)
    if not isinstance(query, exp.Select) or query.args.get("limit") is None:
        return None
    order = query.args.get("order")
    if order is None:
        return None
    if any(isinstance(column, exp.Star) for column in query.expressions):
        raise ValueError("a gold query must name its columns, not use *")
    return _with_tie_breakers(query, is_descending=False), _with_tie_breakers(
        query, is_descending=True
    )


def _with_tie_breakers(query: exp.Select, is_descending: bool) -> str:
    """Appends ORDER BY 1, 2, ... (by output position) to a copy of `query`."""
    variant = query.copy()
    order = variant.args["order"]
    for position in range(1, len(variant.expressions) + 1):
        order.append(
            "expressions", exp.Ordered(this=exp.Literal.number(position), desc=is_descending)
        )
    return variant.sql(dialect=DIALECT)
