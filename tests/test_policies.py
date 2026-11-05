"""The helpers the scripted cheats are built from."""

from tests.scripted.policies import constant_select, first_table


def test_constants_are_text_literals_named_like_the_result() -> None:
    sql = constant_select([{"films": 958}, {"films": 12}])
    assert sql == """SELECT * FROM (VALUES ('958'), ('12')) AS answer("films")"""


def test_a_quote_in_a_constant_is_escaped() -> None:
    assert "('O''Brien', NULL)" in constant_select([{"name": "O'Brien", "city": None}])


def test_first_table_is_the_first_one_the_query_reads() -> None:
    assert first_table("SELECT count(*) FROM film JOIN language USING (language_id)") == "film"


def test_first_table_skips_cte_names() -> None:
    sql = "with top as (select actor_id from film_actor) select * from top"
    assert first_table(sql) == "film_actor"


def test_first_table_skips_table_functions() -> None:
    sql = "select count(*) from generate_series(1, 3) as d(n) join rental on rental.rental_id = d.n"
    assert first_table(sql) == "rental"
