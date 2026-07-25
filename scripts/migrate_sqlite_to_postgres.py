"""Safely migrate existing SQLite rows into PostgreSQL.

Dry-run is the default. Nothing is written unless --execute is supplied.
The tool never creates, drops, truncates, deletes, or updates PostgreSQL rows.
"""

import argparse
import datetime
import json
import os
import pathlib
import sqlite3
import sys

import psycopg
from psycopg import sql
from psycopg.rows import dict_row


ROOT = pathlib.Path(__file__).resolve().parents[1]
DEFAULT_SQLITE = ROOT / "data" / "studio_shop.db"

# Parent tables precede their children. Optional legacy tables are included only
# when they exist in both databases. database_migrations is deliberately absent:
# it describes a database instance, not business data.
TABLE_ORDER = (
    "users",
    "categories",
    "products",
    "orders",
    "order_items",
    "payments",
    "paypal_webhook_events",
    "site_stats",
)
SEQUENCE_TABLES = {
    "users",
    "categories",
    "products",
    "orders",
    "order_items",
    "payments",
    "paypal_webhook_events",
}
SENSITIVE_COLUMNS = {"password", "password_hash", "token"}


def normalize_database_url(value):
    value = (value or "").strip()
    if value.startswith("postgres://"):
        return "postgresql://" + value[len("postgres://") :]
    return value


def quote_sqlite_identifier(name):
    return '"' + name.replace('"', '""') + '"'


def open_sqlite_read_only(path):
    connection = sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA query_only = ON")
    return connection


def sqlite_tables(connection):
    return {
        row["name"]
        for row in connection.execute(
            """
            SELECT name
            FROM sqlite_master
            WHERE type = 'table' AND name NOT LIKE 'sqlite_%'
            """
        )
    }


def postgres_tables(connection):
    return {
        row["table_name"]
        for row in connection.execute(
            """
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = 'public' AND table_type = 'BASE TABLE'
            """
        )
    }


def sqlite_columns(connection, table):
    statement = f"PRAGMA table_info({quote_sqlite_identifier(table)})"
    return [row["name"] for row in connection.execute(statement)]


def postgres_columns(connection, table):
    rows = connection.execute(
        """
        SELECT column_name
        FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = %s
        ORDER BY ordinal_position
        """,
        (table,),
    ).fetchall()
    return [row["column_name"] for row in rows]


def postgres_unique_keys(connection, table):
    """Return every PRIMARY KEY and UNIQUE constraint as ordered column tuples."""
    rows = connection.execute(
        """
        SELECT c.contype, c.conname,
               array_agg(a.attname ORDER BY key_columns.ordinality) AS columns
        FROM pg_constraint AS c
        JOIN pg_class AS t ON t.oid = c.conrelid
        JOIN pg_namespace AS n ON n.oid = t.relnamespace
        JOIN unnest(c.conkey) WITH ORDINALITY AS key_columns(attnum, ordinality)
          ON TRUE
        JOIN pg_attribute AS a
          ON a.attrelid = t.oid AND a.attnum = key_columns.attnum
        WHERE n.nspname = 'public'
          AND t.relname = %s
          AND c.contype IN ('p', 'u')
        GROUP BY c.contype, c.conname
        ORDER BY CASE WHEN c.contype = 'p' THEN 0 ELSE 1 END, c.conname
        """,
        (table,),
    ).fetchall()
    return [tuple(row["columns"]) for row in rows]


def source_rows(connection, table, columns):
    column_sql = ", ".join(quote_sqlite_identifier(column) for column in columns)
    table_sql = quote_sqlite_identifier(table)
    return [
        dict(row)
        for row in connection.execute(f"SELECT {column_sql} FROM {table_sql}")
    ]


def count_rows(connection, table):
    return connection.execute(
        sql.SQL("SELECT COUNT(*) AS count FROM {}").format(sql.Identifier(table))
    ).fetchone()["count"]


def matching_unique_key(connection, table, row, unique_keys):
    """Return the first target unique key matching a source row, if any."""
    for key in unique_keys:
        if not all(column in row for column in key):
            continue
        values = [row[column] for column in key]
        # PostgreSQL UNIQUE constraints normally allow multiple NULLs. Such a key
        # therefore cannot establish that this row already exists.
        if any(value is None for value in values):
            continue
        predicates = [
            sql.SQL("{} = %s").format(sql.Identifier(column)) for column in key
        ]
        query = sql.SQL("SELECT 1 FROM {} WHERE {} LIMIT 1").format(
            sql.Identifier(table),
            sql.SQL(" AND ").join(predicates),
        )
        if connection.execute(query, values).fetchone():
            return key
    return None


def printable_row(row):
    result = {}
    for key, value in row.items():
        if key in SENSITIVE_COLUMNS and value not in (None, ""):
            result[key] = "<preserved; hidden from output>"
        else:
            result[key] = value
    return result


def build_plan(source, target):
    source_table_names = sqlite_tables(source)
    target_table_names = postgres_tables(target)
    plan = []

    source_only = sorted(
        (source_table_names & set(TABLE_ORDER)) - target_table_names
    )
    if source_only:
        raise RuntimeError(
            "Target PostgreSQL is missing source tables: " + ", ".join(source_only)
        )

    for table in TABLE_ORDER:
        if table not in source_table_names or table not in target_table_names:
            continue
        source_column_names = sqlite_columns(source, table)
        target_column_names = set(postgres_columns(target, table))
        columns = [
            column for column in source_column_names if column in target_column_names
        ]
        if not columns:
            raise RuntimeError(f"{table}: source and target share no columns")

        unique_keys = postgres_unique_keys(target, table)
        usable_keys = [
            key for key in unique_keys if all(column in columns for column in key)
        ]
        if not usable_keys:
            raise RuntimeError(
                f"{table}: no PostgreSQL primary/unique key is present in source columns"
            )

        rows = source_rows(source, table, columns)
        pending = []
        skipped = []
        for row in rows:
            matched_key = matching_unique_key(target, table, row, usable_keys)
            if matched_key:
                skipped.append((row, matched_key))
            else:
                pending.append(row)

        plan.append(
            {
                "table": table,
                "columns": columns,
                "unique_keys": usable_keys,
                "source_count": len(rows),
                "target_count": count_rows(target, table),
                "pending": pending,
                "skipped": skipped,
            }
        )
    return plan


def print_plan(plan):
    print("Migration plan (no writes have occurred)")
    print("=" * 72)
    print("sessions: skipped by policy")
    for item in plan:
        print(
            f"{item['table']}: source={item['source_count']}, "
            f"target={item['target_count']}, "
            f"would_insert={len(item['pending'])}, "
            f"already_exists={len(item['skipped'])}"
        )
        print(
            "  conflict keys: "
            + ", ".join("(" + ", ".join(key) + ")" for key in item["unique_keys"])
        )
        for row in item["pending"]:
            print(
                "  INSERT "
                + json.dumps(printable_row(row), ensure_ascii=False, default=str)
            )
        for row, key in item["skipped"]:
            identity = {column: row[column] for column in key}
            print(
                "  SKIP existing "
                + json.dumps(identity, ensure_ascii=False, default=str)
            )


def backup_sqlite(source):
    backup_dir = source.parent / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    destination = backup_dir / f"{source.stem}-{timestamp}{source.suffix}.backup"
    source_connection = open_sqlite_read_only(source)
    destination_connection = sqlite3.connect(destination)
    try:
        source_connection.backup(destination_connection)
    finally:
        destination_connection.close()
        source_connection.close()
    return destination


def insert_pending(connection, item):
    if not item["pending"]:
        return 0
    columns = item["columns"]
    query = sql.SQL(
        "INSERT INTO {} ({}) VALUES ({}) ON CONFLICT DO NOTHING RETURNING 1"
    ).format(
        sql.Identifier(item["table"]),
        sql.SQL(", ").join(map(sql.Identifier, columns)),
        sql.SQL(", ").join(sql.Placeholder() for _ in columns),
    )
    inserted = 0
    for row in item["pending"]:
        result = connection.execute(query, [row[column] for column in columns])
        if result.fetchone():
            inserted += 1
    return inserted


def reset_sequence(connection, table):
    """Move an id sequence to MAX(id), if this table has a serial/identity sequence."""
    sequence = connection.execute(
        "SELECT pg_get_serial_sequence(%s, 'id') AS sequence",
        (f"public.{table}",),
    ).fetchone()["sequence"]
    if not sequence:
        return
    row = connection.execute(
        sql.SQL("SELECT MAX(id) AS maximum FROM {}").format(sql.Identifier(table))
    ).fetchone()
    maximum = row["maximum"]
    connection.execute(
        "SELECT setval(%s, %s, %s)",
        (sequence, maximum if maximum is not None else 1, maximum is not None),
    )


def validate_foreign_keys(connection):
    """Find orphan rows for every PostgreSQL foreign key in migrated tables."""
    constraints = connection.execute(
        """
        SELECT child.relname AS child_table,
               parent.relname AS parent_table,
               array_agg(child_col.attname ORDER BY keys.ordinality) AS child_columns,
               array_agg(parent_col.attname ORDER BY keys.ordinality) AS parent_columns
        FROM pg_constraint AS c
        JOIN pg_class AS child ON child.oid = c.conrelid
        JOIN pg_class AS parent ON parent.oid = c.confrelid
        JOIN pg_namespace AS n ON n.oid = child.relnamespace
        JOIN unnest(c.conkey, c.confkey) WITH ORDINALITY
          AS keys(child_num, parent_num, ordinality) ON TRUE
        JOIN pg_attribute AS child_col
          ON child_col.attrelid = child.oid
         AND child_col.attnum = keys.child_num
        JOIN pg_attribute AS parent_col
          ON parent_col.attrelid = parent.oid
         AND parent_col.attnum = keys.parent_num
        WHERE c.contype = 'f' AND n.nspname = 'public'
        GROUP BY c.oid, child.relname, parent.relname
        """
    ).fetchall()
    migrated_tables = set(TABLE_ORDER)
    for constraint in constraints:
        if constraint["child_table"] not in migrated_tables:
            continue
        joins = [
            sql.SQL("c.{} = p.{}").format(
                sql.Identifier(child_column),
                sql.Identifier(parent_column),
            )
            for child_column, parent_column in zip(
                constraint["child_columns"], constraint["parent_columns"]
            )
        ]
        non_null = [
            sql.SQL("c.{} IS NOT NULL").format(sql.Identifier(column))
            for column in constraint["child_columns"]
        ]
        missing_parent = sql.SQL("p.{} IS NULL").format(
            sql.Identifier(constraint["parent_columns"][0])
        )
        query = sql.SQL(
            "SELECT COUNT(*) AS count FROM {} c LEFT JOIN {} p ON {} WHERE {} AND {}"
        ).format(
            sql.Identifier(constraint["child_table"]),
            sql.Identifier(constraint["parent_table"]),
            sql.SQL(" AND ").join(joins),
            sql.SQL(" AND ").join(non_null),
            missing_parent,
        )
        orphan_count = connection.execute(query).fetchone()["count"]
        if orphan_count:
            raise RuntimeError(
                f"foreign-key validation failed: {constraint['child_table']} -> "
                f"{constraint['parent_table']} has {orphan_count} orphan row(s)"
            )


def execute_migration(source_path, target):
    backup = backup_sqlite(source_path)
    print(f"SQLite backup: {backup}")
    source = open_sqlite_read_only(source_path)
    try:
        # Rebuild the plan inside the same target transaction to close the gap
        # between conflict checks and inserts.
        with target.transaction():
            plan = build_plan(source, target)
            print_plan(plan)
            inserted_counts = {}
            for item in plan:
                inserted_counts[item["table"]] = insert_pending(target, item)
            for item in plan:
                if item["table"] in SEQUENCE_TABLES and "id" in item["columns"]:
                    reset_sequence(target, item["table"])
            validate_foreign_keys(target)
            print("Inserted in this transaction:")
            for table, count in inserted_counts.items():
                print(f"  {table}: {count}")
        print("Migration committed successfully.")
    finally:
        source.close()


def dry_run(source_path, target):
    source = open_sqlite_read_only(source_path)
    try:
        with target.transaction():
            target.execute("SET TRANSACTION READ ONLY")
            plan = build_plan(source, target)
            print_plan(plan)
        print("DRY RUN complete: PostgreSQL was not modified.")
    finally:
        source.close()


def parse_arguments():
    parser = argparse.ArgumentParser(
        description="Idempotent SQLite to PostgreSQL data migration (dry-run by default)"
    )
    parser.add_argument("--sqlite", default=str(DEFAULT_SQLITE))
    parser.add_argument(
        "--execute",
        action="store_true",
        help="perform inserts in one transaction; without this flag the tool is read-only",
    )
    return parser.parse_args()


def main():
    arguments = parse_arguments()
    source_path = pathlib.Path(arguments.sqlite).expanduser().resolve()
    if not source_path.is_file():
        raise FileNotFoundError(f"SQLite file not found: {source_path}")

    database_url = normalize_database_url(os.getenv("DATABASE_URL"))
    if not database_url:
        raise RuntimeError(
            "DATABASE_URL is required. Set it in the environment; never put the "
            "database password in this script."
        )

    with psycopg.connect(database_url, row_factory=dict_row) as target:
        if arguments.execute:
            execute_migration(source_path, target)
        else:
            dry_run(source_path, target)


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(f"Migration failed; PostgreSQL changes were rolled back: {error}", file=sys.stderr)
        raise SystemExit(1)
