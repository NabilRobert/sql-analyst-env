"""A fingerprint of each data copy (requirement D3): if a copy's data
changes, every answer key may change with it, so checks refuse to run on
data that doesn't match the stored fingerprint.

The first five queries are agent-eval-harness's Pagila fingerprint
(agent_eval/targets.py, commit a44cad4). The last two cover what
stack/make_copies.sql also changes: added rows, actor credits and return
dates. Like the harness's, none hashes a timestamp as text, so the result
doesn't depend on the session's time zone."""

import hashlib
import json
from pathlib import Path
from typing import Any

from analyst_env.backbone import REPO_ROOT, BackboneCopy

FINGERPRINT_FILE = REPO_ROOT / "stack" / "fingerprints.json"

FINGERPRINT_QUERIES = (
    "select (select count(*) from customer) as customers, (select count(*) from film) as films,"
    " (select count(*) from rental) as rentals, (select count(*) from payment) as payments,"
    " (select max(rental_id) from rental) as max_rental_id,"
    " (select max(payment_id) from payment) as max_payment_id",
    "select md5(string_agg(customer_id || ',' || first_name || ',' || last_name || ','"
    " || coalesce(email, ''), '|' order by customer_id)) as customers_md5 from customer",
    "select md5(string_agg(film_id || ',' || title || ',' || rental_rate || ','"
    " || coalesce(length, 0) || ',' || rating, '|' order by film_id)) as films_md5 from film",
    "select md5(string_agg(rental_id || ',' || inventory_id || ',' || customer_id, '|'"
    " order by rental_id)) as rentals_md5 from rental",
    "select md5(string_agg(payment_id || ',' || amount || ',' || customer_id, '|'"
    " order by payment_id)) as payments_md5 from payment",
    "select (select count(*) from actor) as actors, (select count(*) from country) as countries,"
    " (select count(*) from city) as cities, (select count(*) from film_actor) as credits",
    "select md5(string_agg(rental_id || ','"
    " || coalesce(extract(epoch from return_date)::bigint, 0), '|' order by rental_id))"
    " as returns_md5 from rental",
)


class FingerprintError(RuntimeError):
    pass


async def fingerprint(copy: BackboneCopy) -> str:
    parts: list[dict[str, Any]] = []
    for sql in FINGERPRINT_QUERIES:
        result = await copy.run_query(sql)
        if not result.is_success:
            raise FingerprintError(f"{copy.name}: fingerprint query refused: {result.error}")
        parts.extend(result.rows)
    text = json.dumps(parts, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def load_stored_fingerprints(path: Path = FINGERPRINT_FILE) -> dict[str, str]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_fingerprints(fingerprints: dict[str, str], path: Path = FINGERPRINT_FILE) -> None:
    path.write_text(json.dumps(fingerprints, indent=2, sort_keys=True) + "\n", encoding="utf-8")


async def mismatched_copies(copies: list[BackboneCopy], stored: dict[str, str]) -> list[str]:
    """The copies whose data isn't the data the stored fingerprints
    describe (requirement D3). Returned, not raised: an error raised while
    MCP sessions are open reaches the caller wrapped in an ExceptionGroup."""
    return [copy.name for copy in copies if stored.get(copy.name) != await fingerprint(copy)]


def mismatch_error(names: list[str]) -> FingerprintError:
    return FingerprintError(
        f"{', '.join(names)}: data doesn't match stack/fingerprints.json. Rebuild the stack with "
        "`docker compose down -v && docker compose up -d --wait`, or, if the copy script "
        "changed on purpose, run `uv run analyst-env fingerprint --write`"
    )
