"""One-time SQLite to PostgreSQL migration. This is never run at application startup."""

import argparse
import datetime
import os
import pathlib
import shutil
import sqlite3
import sys


ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import database  # noqa: E402
from migrations.runner import run_migrations  # noqa: E402


TABLES = ("users", "products", "orders", "order_items", "site_stats", "sessions")


def sqlite_columns(connection, table):
    return [row[1] for row in connection.execute(f"PRAGMA table_info({table})")]


def postgres_columns(connection, table):
    return [
        row["column_name"]
        for row in connection.execute(
            """
            SELECT column_name
            FROM information_schema.columns
            WHERE table_schema = 'public' AND table_name = ?
            ORDER BY ordinal_position
            """,
            (table,),
        ).fetchall()
    ]


def backup_sqlite(source):
    backup_dir = source.parent / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    target = backup_dir / f"{source.stem}-{timestamp}{source.suffix}.backup"
    shutil.copy2(source, target)
    return target


def migrate(source_path):
    if not os.getenv("DATABASE_URL"):
        raise RuntimeError("缺少 DATABASE_URL；搬移工具不允許使用 SQLite 目標")
    source = pathlib.Path(source_path).resolve()
    if not source.is_file():
        raise FileNotFoundError(f"找不到 SQLite：{source}")
    backup = backup_sqlite(source)
    run_migrations(str(source))

    sqlite_connection = sqlite3.connect(str(source))
    sqlite_connection.row_factory = sqlite3.Row
    source_counts = {
        table: sqlite_connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        for table in TABLES
    }

    with database.connect(str(source)) as target:
        target_counts = {
            table: target.execute(f"SELECT COUNT(*) AS count FROM {table}").fetchone()["count"]
            for table in TABLES
        }
        populated = {table: count for table, count in target_counts.items() if count}
        if populated:
            raise RuntimeError(f"PostgreSQL 目標不是空資料庫，已停止：{populated}")

        for table in TABLES:
            source_columns = sqlite_columns(sqlite_connection, table)
            destination_columns = set(postgres_columns(target, table))
            columns = [column for column in source_columns if column in destination_columns]
            column_sql = ", ".join(columns)
            placeholders = ", ".join("?" for _ in columns)
            rows = sqlite_connection.execute(f"SELECT {column_sql} FROM {table}").fetchall()
            if rows:
                target.executemany(
                    f"INSERT INTO {table} ({column_sql}) VALUES ({placeholders})",
                    [tuple(row[column] for column in columns) for row in rows],
                )

        for table in ("users", "products", "orders", "order_items"):
            target.execute(
                f"""
                SELECT setval(
                    pg_get_serial_sequence('{table}', 'id'),
                    COALESCE(MAX(id), 1),
                    MAX(id) IS NOT NULL
                )
                FROM {table}
                """
            )

        orphan_items = target.execute(
            """
            SELECT COUNT(*) AS count
            FROM order_items i
            LEFT JOIN orders o ON o.id = i.order_id
            LEFT JOIN products p ON p.id = i.product_id
            WHERE o.id IS NULL OR p.id IS NULL
            """
        ).fetchone()["count"]
        amount_mismatches = target.execute(
            """
            SELECT COUNT(*) AS count
            FROM orders o
            WHERE o.total != COALESCE(
                (SELECT SUM(i.subtotal) FROM order_items i WHERE i.order_id = o.id), 0
            )
            """
        ).fetchone()["count"]
        if orphan_items or amount_mismatches:
            raise RuntimeError(
                f"搬移驗證失敗：orphan_items={orphan_items}, amount_mismatches={amount_mismatches}"
            )

    with database.connect(str(source)) as target:
        destination_counts = {
            table: target.execute(f"SELECT COUNT(*) AS count FROM {table}").fetchone()["count"]
            for table in TABLES
        }
    if source_counts != destination_counts:
        raise RuntimeError(
            f"搬移筆數不一致：source={source_counts}, destination={destination_counts}"
        )
    return backup, source_counts, destination_counts


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--sqlite", default=str(ROOT / "data" / "studio_shop.db"))
    arguments = parser.parse_args()
    backup_path, before, after = migrate(arguments.sqlite)
    print(f"SQLite backup retained at: {backup_path}")
    print(f"Source counts: {before}")
    print(f"PostgreSQL counts: {after}")
    print("Foreign keys and order totals verified.")
