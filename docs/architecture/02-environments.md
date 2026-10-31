# 02. Environments, migrations and testing

Date: 2026-10-13
Status: accepted

## Context

Phase 02 adds the first real table: learning environments. Every later feature
belongs to an environment, so this phase also sets the patterns the rest of the
schema will follow: how tables are created and changed, how ids and timestamps
are generated, and how code that writes to the database is tested.

## Decisions

### Every schema change is an Alembic migration

Tables are created and altered only by versioned migration scripts in
`api/migrations/versions/`, never by hand and never by asking SQLAlchemy to
create tables from the models. The migrations are the history of the schema,
and running them is the same command on a laptop, in CI and in a deployment.

The first migration was written by hand. Later ones can start from
`alembic revision --autogenerate`, but are always read before being applied.

### Models and migrations are checked against each other

The SQLAlchemy models describe the tables; the migrations create them. Nothing
forces the two to agree, so `alembic check` compares them, in CI and in the test
suite. By default it ignores column defaults, which would let a model and its
table disagree about how ids or timestamps are filled in. Default comparison is
switched on, and was confirmed to catch a removed default without false alarms.

### The database generates ids and timestamps

Ids are UUIDs from Postgres's `gen_random_uuid()`, and both timestamps default
to the time of insertion. Because the database fills them in, every way of
inserting a row produces a complete one, whether through the API, psql or a
database client. UUIDs also keep ids from being guessable from a URL.

`updated_at` is refreshed on each change with `statement_timestamp()` rather
than `now()`. In Postgres, `now()` is fixed at the start of a transaction, so a
change made later in the same transaction would not move it.

### Tests use their own database, rolled back after every test

Tests run against a separate database named after the development one with
`_test` appended. Each run drops it, recreates it empty, and builds it solely by
running the migrations, so a model change that ships without its migration fails
the tests. A guard refuses to run against any database whose name does not end
in `_test`.

Each test runs inside a transaction that is rolled back when it ends. Code under
test still commits normally; inside the outer transaction, each commit only
releases a savepoint. Every test starts from an empty database, nothing is ever
really written, and the suite runs in under a second.

Alternatives considered:

- The development database: tests would either see real data or destroy it.
- SQLite in memory: fast, but not Postgres. It has no pgvector, and different
  UUID and timestamp behaviour would make passing tests prove little.
- A new Postgres container per run: the cleanest isolation, but an extra
  dependency and slower, for a benefit this project does not yet need.

The rollback approach cannot test behaviour that depends on a second connection
seeing committed data, such as a background worker. Those tests, when they
arrive with background processing, will clean up by deleting rows instead.

### One configuration file for every part

Backend, frontend and Docker Compose all read the single `.env` at the
repository root. Next.js normally reads only its own folder, so its config loads
the root file explicitly with Node's built-in loader. A real environment
variable still takes precedence, which is what a deployment needs.

## Consequences

- Running `alembic upgrade head` is part of setting up and of every pull that
  adds a migration.
- Any table that belongs to an environment must be designed to be deleted with
  it. The test that deletes one environment and checks the others are untouched
  is extended as those tables arrive.
- The frontend's types mirror the backend's schemas by hand. Generating them
  from the API's published schema becomes worthwhile once more endpoints exist.
