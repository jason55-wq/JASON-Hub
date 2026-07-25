import os
import sqlite3
import threading


_pool = None
_pool_url = None
_pool_lock = threading.Lock()


def normalize_database_url(url):
    url = (url or "").strip()
    if url.startswith("postgres://"):
        return "postgresql://" + url[len("postgres://") :]
    return url


def production_mode():
    return (
        os.getenv("RENDER", "").lower() == "true"
        or os.getenv("APP_ENV", "").lower() == "production"
    )


def configured_database_url():
    url = normalize_database_url(os.getenv("DATABASE_URL"))
    if production_mode() and not url:
        raise RuntimeError("production/Render 環境缺少 DATABASE_URL，拒絕使用本機 SQLite")
    return url


def database_backend():
    return "postgresql" if configured_database_url() else "sqlite"


def _postgres_pool(url):
    global _pool, _pool_url
    with _pool_lock:
        if _pool is not None and _pool_url == url:
            return _pool
        try:
            from psycopg.rows import dict_row
            from psycopg_pool import ConnectionPool
        except ImportError as exc:
            raise RuntimeError(
                "使用 PostgreSQL 需要安裝 requirements.txt 中的 psycopg 與 psycopg_pool"
            ) from exc
        if _pool is not None:
            _pool.close()
        _pool = ConnectionPool(
            conninfo=url,
            min_size=1,
            max_size=int(os.getenv("DATABASE_POOL_SIZE", "10")),
            max_lifetime=1800,
            max_idle=300,
            timeout=10,
            kwargs={"row_factory": dict_row},
            check=ConnectionPool.check_connection,
            open=True,
        )
        _pool_url = url
        return _pool


def _postgres_sql(sql):
    stripped = sql.strip().upper()
    if stripped == "BEGIN IMMEDIATE":
        return "BEGIN"
    return sql.replace("CURRENT_TIMESTAMP", "CURRENT_TIMESTAMP::text").replace("?", "%s")


class PostgresConnection:
    def __init__(self, url):
        self._context = _postgres_pool(url).connection()
        self._connection = None

    def __enter__(self):
        self._connection = self._context.__enter__()
        return self

    def __exit__(self, exc_type, exc, traceback):
        return self._context.__exit__(exc_type, exc, traceback)

    def execute(self, sql, parameters=()):
        return self._connection.execute(_postgres_sql(sql), parameters)

    def executemany(self, sql, parameters):
        return self._connection.executemany(_postgres_sql(sql), parameters)


def connect(sqlite_path):
    url = configured_database_url()
    if url:
        return PostgresConnection(url)
    connection = sqlite3.connect(sqlite_path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def is_integrity_error(exc):
    if isinstance(exc, sqlite3.IntegrityError):
        return True
    try:
        from psycopg import IntegrityError
    except ImportError:
        return False
    return isinstance(exc, IntegrityError)


def close_pool():
    global _pool, _pool_url
    with _pool_lock:
        if _pool is not None:
            _pool.close()
        _pool = None
        _pool_url = None
