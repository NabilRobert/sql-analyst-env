"""The rewrite behind task check C3 (a tie at a cut)."""

import pytest

from analyst_env.sql_variants import tie_break_variants


def test_a_query_without_limit_has_no_variants() -> None:
    assert tie_break_variants("select rating, count(*) from film group by rating") is None


def test_a_limit_without_order_has_no_variants() -> None:
    assert tie_break_variants("select title from film limit 3") is None


def test_each_output_column_is_appended_both_ways() -> None:
    variants = tie_break_variants("select title, length from film order by length desc limit 3")
    assert variants == (
        "SELECT title, length FROM film ORDER BY length DESC, 1 ASC, 2 ASC LIMIT 3",
        "SELECT title, length FROM film"
        " ORDER BY length DESC, 1 DESC NULLS LAST, 2 DESC NULLS LAST LIMIT 3",
    )


def test_an_inner_limit_is_left_alone() -> None:
    sql = "select count(*) from (select film_id from film order by length limit 5) t"
    assert tie_break_variants(sql) is None


def test_a_gold_query_with_star_is_refused() -> None:
    with pytest.raises(ValueError, match="name its columns"):
        tie_break_variants("select * from film order by length desc limit 1")
