"""The helpers the scripted cheats are built from."""

from tests.scripted.policies import constant_select, first_table


def test_constants_are_text_literals_named_like_the_result() -> None:
    sql = constant_select([{"films": 958}, {"films": 12}])
    assert sql == """SELECT * FROM (VALUES ('958'), ('12')) AS answer("films")"""


def test_a_quote_in_a_constant_is_escaped() -> None:
    assert "('O''Brien', NULL)" in constant_select([{"name": "O'Brien", "city": None}])


def test_first_table_is_the_first_one_the_query_reads() -> None:
    assert first_table("SELECT count(*) FROM film JOIN language USING (language_id)") == "film"
