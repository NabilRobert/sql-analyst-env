-- Turns a fresh copy of Pagila into a perturbed one (ADR-009), so a model
-- that memorised public Pagila's answers gets them wrong, and a query that
-- hard-codes an answer can't match on both copies.
--
-- Run by stack/setup_stack.py, once per copy, with psql variables:
--   seed               text that decides which rows are touched
--   film_drop_per_256  share of films deleted, out of 256
--   length_offset      minutes added to every film's length
--   payment_scale      multiplier for every payment amount
--   new_countries, new_actors, new_canada_cities   rows to add
--
-- The schema, the keys, and every value a question names (categories,
-- languages, ratings, 'Canada', actor 1) are kept, so every question
-- still makes sense. Which rows go is decided by a hash of the seed and
-- the row's id, so the same seed always gives the same copy.

\set ON_ERROR_STOP on
BEGIN;

-- True for about per_256/256 of ids, decided by the seed alone.
CREATE FUNCTION pg_temp.is_picked(seed text, salt text, id bigint, per_256 int)
RETURNS boolean LANGUAGE sql IMMUTABLE AS $$
    SELECT get_byte(decode(md5(seed || ':' || salt || ':' || id), 'hex'), 0) < per_256
$$;

-- A few percent of films go, a different share per copy, with everything
-- that hangs off them.
CREATE TEMP TABLE dropped_films AS
    SELECT film_id FROM film WHERE pg_temp.is_picked(:'seed', 'film', film_id, :film_drop_per_256);
-- About 3% of customers go, with their rentals and payments.
CREATE TEMP TABLE dropped_customers AS
    SELECT customer_id FROM customer
    WHERE pg_temp.is_picked(:'seed', 'customer', customer_id, 8);
-- Plus about 4% of the remaining rentals, with their payments.
CREATE TEMP TABLE dropped_rentals AS
    SELECT r.rental_id FROM rental r
    JOIN inventory i ON i.inventory_id = r.inventory_id
    WHERE i.film_id IN (SELECT film_id FROM dropped_films)
       OR r.customer_id IN (SELECT customer_id FROM dropped_customers)
       OR pg_temp.is_picked(:'seed', 'rental', r.rental_id, 10);

DELETE FROM payment
WHERE rental_id IN (SELECT rental_id FROM dropped_rentals)
   OR customer_id IN (SELECT customer_id FROM dropped_customers);
DELETE FROM rental WHERE rental_id IN (SELECT rental_id FROM dropped_rentals);
DELETE FROM inventory WHERE film_id IN (SELECT film_id FROM dropped_films);
DELETE FROM film_actor WHERE film_id IN (SELECT film_id FROM dropped_films);
DELETE FROM film_category WHERE film_id IN (SELECT film_id FROM dropped_films);
DELETE FROM film WHERE film_id IN (SELECT film_id FROM dropped_films);
DELETE FROM customer WHERE customer_id IN (SELECT customer_id FROM dropped_customers);

-- About 8% of actor credits go, so per-actor counts move.
DELETE FROM film_actor
WHERE pg_temp.is_picked(:'seed', 'credit', actor_id::bigint * 100000 + film_id, 20);

-- Lengths move by the copy's offset, plus -2 to +2 minutes per film, so
-- averages and maximums change, and differ between copies.
UPDATE film
SET length = length + :length_offset
    + (get_byte(decode(md5(:'seed' || ':length:' || film_id), 'hex'), 0) % 5) - 2
WHERE length IS NOT NULL;

-- About 6% of films move to the next rating, so per-rating answers change.
UPDATE film
SET rating = (enum_range(NULL::mpaa_rating))[
    array_position(enum_range(NULL::mpaa_rating), rating) % cardinality(enum_range(NULL::mpaa_rating)) + 1]
WHERE rating IS NOT NULL AND pg_temp.is_picked(:'seed', 'rating', film_id, 15);

-- About 10% of returns come back a day later, so lateness changes.
UPDATE rental SET return_date = return_date + interval '1 day'
WHERE return_date IS NOT NULL AND pg_temp.is_picked(:'seed', 'return', rental_id, 26);

-- Every payment scales, so every total changes.
UPDATE payment SET amount = round(amount * :payment_scale, 2);

-- Added rows, in different numbers per copy, so plain counts differ.
INSERT INTO country (country)
    SELECT (ARRAY['Arcadia', 'Brevonia', 'Caldoria'])[n] FROM generate_series(1, :new_countries) n;
INSERT INTO actor (first_name, last_name)
    SELECT (ARRAY['MAYA', 'OREN', 'TESSA'])[n], (ARRAY['QUINN', 'VALE', 'MORROW'])[n]
    FROM generate_series(1, :new_actors) n;
INSERT INTO city (city, country_id)
    SELECT (ARRAY['Port Alder', 'Birch Falls', 'Cedar Bay'])[n], country_id
    FROM generate_series(1, :new_canada_cities) n, country WHERE country = 'Canada';

COMMIT;
