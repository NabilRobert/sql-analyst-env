"""The strict grader: what counts as the same answer."""

from decimal import Decimal

from analyst_env.grading import results_match, rows_equal_strict, rows_equal_strict_in_order


def test_same_rows_in_another_order_match() -> None:
    assert rows_equal_strict([{"a": 1}, {"a": 2}], [{"a": 2}, {"a": 1}])


def test_a_number_written_three_ways_matches() -> None:
    assert rows_equal_strict([{"n": "5.00"}], [{"n": Decimal("5")}])
    assert rows_equal_strict([{"n": 5.0}], [{"n": 5}])


def test_column_names_are_not_compared() -> None:
    assert rows_equal_strict([{"total": 3}], [{"sum": 3}])


def test_an_extra_column_fails() -> None:
    assert not rows_equal_strict([{"name": "Horror", "id": 11}], [{"name": "Horror"}])


def test_swapped_columns_fail() -> None:
    assert not rows_equal_strict([{"n": 5, "name": "a"}], [{"name": "a", "n": 5}])


def test_an_extra_row_fails() -> None:
    assert not rows_equal_strict([{"a": 1}, {"a": 2}], [{"a": 1}])


def test_rounding_is_not_forgiven() -> None:
    assert not rows_equal_strict([{"x": "290.65"}], [{"x": "290.6512"}])


def test_in_order_comparison_fails_on_reordered_rows() -> None:
    assert not rows_equal_strict_in_order([{"a": 1}, {"a": 2}], [{"a": 2}, {"a": 1}])


def test_results_match_uses_order_only_when_asked() -> None:
    reordered = ([{"a": 1}, {"a": 2}], [{"a": 2}, {"a": 1}])
    assert results_match(*reordered, is_ordered=False)
    assert not results_match(*reordered, is_ordered=True)
