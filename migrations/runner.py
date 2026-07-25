import database


ORDER_PAYMENT_COLUMNS = (
    ("review_status", "TEXT NOT NULL DEFAULT 'pending'"),
    ("merchant_trade_no", "TEXT"),
    ("merchant_trade_date", "TEXT"),
    ("checkout_token", "TEXT"),
    ("payment_method", "TEXT NOT NULL DEFAULT 'manual'"),
    ("payment_status", "TEXT NOT NULL DEFAULT 'pending'"),
    ("trade_no", "TEXT"),
    ("ecpay_trade_no", "TEXT"),
    ("paid_at", "TEXT"),
    ("payment_amount", "INTEGER"),
    ("payment_response", "TEXT"),
    ("payment_error", "TEXT"),
    ("payment_callback_processed_at", "TEXT"),
    ("inventory_deducted", "INTEGER NOT NULL DEFAULT 1"),
    ("updated_at", "TEXT"),
)

PAYPAL_ORDER_COLUMNS = (
    ("paypal_order_id", "TEXT"),
    ("paypal_capture_id", "TEXT"),
    ("paypal_invoice_id", "TEXT"),
    ("paypal_currency", "TEXT"),
    ("paypal_amount", "TEXT"),
    ("paypal_request_id", "TEXT"),
    ("paypal_capture_request_id", "TEXT"),
)


def _id_column(backend):
    return "SERIAL PRIMARY KEY" if backend == "postgresql" else "INTEGER PRIMARY KEY AUTOINCREMENT"


def _column_names(connection, backend, table):
    if backend == "postgresql":
        rows = connection.execute(
            """
            SELECT column_name
            FROM information_schema.columns
            WHERE table_schema = 'public' AND table_name = ?
            """,
            (table,),
        ).fetchall()
        return {row["column_name"] for row in rows}
    return {row["name"] for row in connection.execute(f"PRAGMA table_info({table})").fetchall()}


def migration_001_initial_schema(connection, backend):
    identifier = _id_column(backend)
    statements = (
        f"""
        CREATE TABLE IF NOT EXISTS users (
            id {identifier},
            username TEXT NOT NULL UNIQUE,
            email TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL,
            role TEXT NOT NULL DEFAULT 'member',
            status TEXT NOT NULL DEFAULT 'pending',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS sessions (
            token TEXT PRIMARY KEY,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            expires_at BIGINT NOT NULL
        )
        """,
        f"""
        CREATE TABLE IF NOT EXISTS products (
            id {identifier},
            name TEXT NOT NULL,
            category TEXT NOT NULL DEFAULT '工作室選品',
            description TEXT NOT NULL DEFAULT '',
            price INTEGER NOT NULL,
            stock INTEGER NOT NULL DEFAULT 0,
            status TEXT NOT NULL DEFAULT 'draft',
            featured INTEGER NOT NULL DEFAULT 0,
            preview_url TEXT NOT NULL DEFAULT '',
            image_url TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """,
        f"""
        CREATE TABLE IF NOT EXISTS orders (
            id {identifier},
            user_id INTEGER NOT NULL REFERENCES users(id),
            customer_name TEXT NOT NULL,
            phone TEXT NOT NULL,
            address TEXT NOT NULL,
            note TEXT NOT NULL DEFAULT '',
            total INTEGER NOT NULL,
            status TEXT NOT NULL DEFAULT 'new',
            review_status TEXT NOT NULL DEFAULT 'pending',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            merchant_trade_no TEXT,
            merchant_trade_date TEXT,
            checkout_token TEXT,
            payment_method TEXT NOT NULL DEFAULT 'manual',
            payment_status TEXT NOT NULL DEFAULT 'pending',
            trade_no TEXT,
            ecpay_trade_no TEXT,
            paid_at TEXT,
            payment_amount INTEGER,
            payment_response TEXT,
            payment_error TEXT,
            payment_callback_processed_at TEXT,
            inventory_deducted INTEGER NOT NULL DEFAULT 1,
            updated_at TEXT
        )
        """,
        f"""
        CREATE TABLE IF NOT EXISTS order_items (
            id {identifier},
            order_id INTEGER NOT NULL REFERENCES orders(id) ON DELETE CASCADE,
            product_id INTEGER NOT NULL REFERENCES products(id),
            product_name TEXT NOT NULL,
            quantity INTEGER NOT NULL,
            unit_price INTEGER NOT NULL,
            subtotal INTEGER NOT NULL
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS site_stats (
            key TEXT PRIMARY KEY,
            value INTEGER NOT NULL DEFAULT 0,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """,
    )
    for statement in statements:
        connection.execute(statement)


def migration_002_legacy_columns_and_indexes(connection, backend):
    order_columns = _column_names(connection, backend, "orders")
    for name, definition in ORDER_PAYMENT_COLUMNS:
        if name not in order_columns:
            connection.execute(f"ALTER TABLE orders ADD COLUMN {name} {definition}")
    product_columns = _column_names(connection, backend, "products")
    if "preview_url" not in product_columns:
        connection.execute("ALTER TABLE products ADD COLUMN preview_url TEXT NOT NULL DEFAULT ''")
    if "image_url" not in product_columns:
        connection.execute("ALTER TABLE products ADD COLUMN image_url TEXT NOT NULL DEFAULT ''")
    connection.execute(
        "UPDATE orders SET updated_at = COALESCE(updated_at, created_at, CURRENT_TIMESTAMP)"
    )
    connection.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS idx_orders_merchant_trade_no
        ON orders(merchant_trade_no)
        WHERE merchant_trade_no IS NOT NULL
        """
    )
    connection.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS idx_orders_checkout_token
        ON orders(checkout_token)
        WHERE checkout_token IS NOT NULL
        """
    )


def migration_003_paypal_checkout(connection, backend):
    order_columns = _column_names(connection, backend, "orders")
    for name, definition in PAYPAL_ORDER_COLUMNS:
        if name not in order_columns:
            connection.execute(f"ALTER TABLE orders ADD COLUMN {name} {definition}")

    identifier = _id_column(backend)
    connection.execute(
        f"""
        CREATE TABLE IF NOT EXISTS paypal_webhook_events (
            id {identifier},
            event_id TEXT NOT NULL UNIQUE,
            event_type TEXT NOT NULL,
            resource_id TEXT,
            processing_status TEXT NOT NULL DEFAULT 'received',
            error_message TEXT,
            received_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            processed_at TEXT
        )
        """
    )
    for column in ("paypal_order_id", "paypal_capture_id", "paypal_invoice_id"):
        connection.execute(
            f"""
            CREATE UNIQUE INDEX IF NOT EXISTS idx_orders_{column}
            ON orders({column})
            WHERE {column} IS NOT NULL
            """
        )


MIGRATIONS = (
    (1, "initial_schema", migration_001_initial_schema),
    (2, "legacy_columns_and_indexes", migration_002_legacy_columns_and_indexes),
    (3, "paypal_checkout", migration_003_paypal_checkout),
)


def run_migrations(sqlite_path):
    backend = database.database_backend()
    with database.connect(sqlite_path) as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS database_migrations (
                version INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        applied = {
            row["version"]
            for row in connection.execute("SELECT version FROM database_migrations").fetchall()
        }
        for version, name, migrate in MIGRATIONS:
            if version in applied:
                continue
            migrate(connection, backend)
            connection.execute(
                "INSERT INTO database_migrations (version, name) VALUES (?, ?)",
                (version, name),
            )
    return backend
