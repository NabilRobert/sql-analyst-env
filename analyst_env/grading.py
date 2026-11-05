"""Decides whether two query results are the same answer (ADR-008).

Copied from agent-eval-harness's agent_eval/grading.py at commit a44cad4
(grader version 4): `_normalize_value`, `_exact_key` and
`rows_equal_strict`. Only the strict comparison is taken. The lenient one
tolerates extra columns, which is right for a benchmark and wrong for a
reward: a model would learn to return wide rows. `rows_equal_strict_in_order`
is new, for questions that ask for an order."""

from decimal import MAX_EMAX, MAX_PREC, MIN_EMIN, Context, Decimal, InvalidOperation
from typing import Any

# Strict comparison rewrites a number without changing it, so it can't use
# the default context, which rounds to 28 digits.
_EXACT_CONTEXT = Context(prec=MAX_PREC, Emax=MAX_EMAX, Emin=MIN_EMIN)

Row = dict[str, Any]


def _normalize_value(value: Any) -> Any:
    """Numbers can arrive as numbers or as numeric strings (JSON has no
    Decimal), so both are turned into Decimal before comparing.
    Tradeoff: a numeric-looking string (a zip code with a leading zero)
    loses that distinction. NaN and Infinity stay as they came: they aren't
    numbers to compare, and Decimal arithmetic on them raises."""
    number: Decimal | None = None
    if isinstance(value, (int, float, Decimal)) and not isinstance(value, bool):
        number = Decimal(str(value))
    elif isinstance(value, str):
        try:
            number = Decimal(value)
        except InvalidOperation:
            return value
    if number is not None and number.is_finite():
        return number
    return value


def _exact_key(value: Any) -> str:
    """Text that's the same for two values exactly when they're equal, so
    rows can be sorted and compared. 5, 5.0 and "5.00" are one number
    written three ways; rewriting a Decimal in its shortest form is exact."""
    normalized = _normalize_value(value)
    if not isinstance(normalized, Decimal):
        return repr(normalized)
    if not normalized:  # -0 and 0 are the same number
        return "0"
    return str(normalized.normalize(_EXACT_CONTEXT))


def _row_keys(rows: list[Row]) -> list[str]:
    return [repr([_exact_key(v) for v in row.values()]) for row in rows]


def rows_equal_strict(actual: list[Row], expected: list[Row]) -> bool:
    """Same columns in the same order, exactly equal values, rows in any
    order. Column names aren't compared: an alias is a naming choice."""
    return sorted(_row_keys(actual)) == sorted(_row_keys(expected))


def rows_equal_strict_in_order(actual: list[Row], expected: list[Row]) -> bool:
    """rows_equal_strict, but the rows must also come in the same order."""
    return _row_keys(actual) == _row_keys(expected)


def results_match(actual: list[Row], expected: list[Row], is_ordered: bool) -> bool:
    if is_ordered:
        return rows_equal_strict_in_order(actual, expected)
    return rows_equal_strict(actual, expected)
