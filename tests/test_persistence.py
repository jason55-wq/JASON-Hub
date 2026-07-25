import os
import tempfile
import unittest
from unittest.mock import patch

import database
import server


class PersistenceTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.original_db_path = server.DB_PATH
        server.DB_PATH = os.path.join(self.temp_dir.name, "persistence.db")
        self.environment = patch.dict(
            os.environ,
            {"RENDER": "false", "APP_ENV": "development"},
            clear=False,
        )
        self.environment.start()
        os.environ.pop("DATABASE_URL", None)

    def tearDown(self):
        server.DB_PATH = self.original_db_path
        self.environment.stop()
        self.temp_dir.cleanup()

    def test_restart_and_repeated_migration_preserve_all_records(self):
        server.init_db()
        with server.db() as connection:
            user_id = server.insert_and_get_id(
                connection,
                """
                INSERT INTO users (username, email, password_hash, role, status)
                VALUES (?, ?, ?, 'member', 'approved')
                """,
                ("persistent-user", "persistent@example.com", server.hash_password("password")),
            )
            product_id = server.insert_and_get_id(
                connection,
                """
                INSERT INTO products
                (name, category, description, price, stock, status, featured, preview_url, image_url)
                VALUES ('Persistent product', 'Test', '', 25, 9, 'active', 0, '', '')
                """
            )
            order_id = server.insert_and_get_id(
                connection,
                """
                INSERT INTO orders
                (user_id, customer_name, phone, address, total, status, payment_method,
                 payment_status, inventory_deducted)
                VALUES (?, 'Buyer', '0900000000', 'Address', 25, 'paid',
                        'ecpay_credit', 'paid', 1)
                """,
                (user_id,),
            )
            connection.execute(
                """
                INSERT INTO order_items
                (order_id, product_id, product_name, quantity, unit_price, subtotal)
                VALUES (?, ?, 'Persistent product', 1, 25, 25)
                """,
                (order_id, product_id),
            )

        server.init_db()
        server.init_db()
        with server.db() as connection:
            self.assertEqual(
                connection.execute(
                    "SELECT COUNT(*) AS count FROM users WHERE id = ?", (user_id,)
                ).fetchone()["count"],
                1,
            )
            self.assertEqual(
                connection.execute(
                    "SELECT price FROM products WHERE id = ?", (product_id,)
                ).fetchone()["price"],
                25,
            )
            order = connection.execute(
                "SELECT total, payment_status FROM orders WHERE id = ?", (order_id,)
            ).fetchone()
            self.assertEqual((order["total"], order["payment_status"]), (25, "paid"))
            self.assertEqual(
                connection.execute(
                    "SELECT COUNT(*) AS count FROM database_migrations"
                ).fetchone()["count"],
                3,
            )

    def test_explicit_seed_is_idempotent_and_does_not_overwrite(self):
        server.init_db()
        server.seed_defaults()
        with server.db() as connection:
            admin = connection.execute(
                "SELECT id, password_hash FROM users WHERE username = ?",
                (server.DEFAULT_ADMIN_USERNAME,),
            ).fetchone()
            product = connection.execute(
                "SELECT id FROM products WHERE name = ?", (server.TEST_PRODUCT[0],)
            ).fetchone()
            connection.execute(
                "UPDATE products SET price = 77, stock = 3 WHERE id = ?", (product["id"],)
            )
        server.seed_defaults()
        with server.db() as connection:
            admin_after = connection.execute(
                "SELECT password_hash FROM users WHERE id = ?", (admin["id"],)
            ).fetchone()
            product_after = connection.execute(
                "SELECT price, stock FROM products WHERE id = ?", (product["id"],)
            ).fetchone()
        self.assertEqual(admin_after["password_hash"], admin["password_hash"])
        self.assertEqual((product_after["price"], product_after["stock"]), (77, 3))

    def test_render_without_database_url_fails_instead_of_using_sqlite(self):
        with patch.dict(os.environ, {"RENDER": "true"}, clear=False):
            os.environ.pop("DATABASE_URL", None)
            with self.assertRaisesRegex(RuntimeError, "缺少 DATABASE_URL"):
                server.init_db()
        self.assertFalse(os.path.exists(server.DB_PATH))

    def test_postgres_connection_failure_never_falls_back_to_sqlite(self):
        with patch.dict(
            os.environ,
            {"RENDER": "true", "DATABASE_URL": "postgres://invalid/db"},
            clear=False,
        ), patch.object(database, "_postgres_pool", side_effect=RuntimeError("connection failed")):
            with self.assertRaisesRegex(RuntimeError, "connection failed"):
                server.init_db()
        self.assertFalse(os.path.exists(server.DB_PATH))

    def test_postgres_url_is_normalized(self):
        self.assertEqual(
            database.normalize_database_url("postgres://user:pass@host/db"),
            "postgresql://user:pass@host/db",
        )
        self.assertEqual(
            database._postgres_sql(
                "UPDATE orders SET updated_at = CURRENT_TIMESTAMP WHERE id = ?"
            ),
            "UPDATE orders SET updated_at = CURRENT_TIMESTAMP::text WHERE id = %s",
        )


if __name__ == "__main__":
    unittest.main()
