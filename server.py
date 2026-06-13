import base64
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse, unquote
import hashlib
import hmac
import json
import os
import secrets
import sqlite3
import time
import traceback


BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
DB_PATH = os.path.join(DATA_DIR, "studio_shop.db")
PRODUCTS_JSON_PATH = os.path.join(DATA_DIR, "products.json")
STATIC_DIR = os.path.join(BASE_DIR, "static")
SESSION_TTL = 60 * 60 * 24 * 7
DEFAULT_ADMIN_USERNAME = "we252668"
DEFAULT_ADMIN_PASSWORD = "edc25610731"
DEFAULT_ADMIN_EMAIL = "123@studio.local"
ORDER_REVIEW_STATUSES = {"pending", "approved", "rejected"}


def db():
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    return con


def hash_password(password, salt=None):
    salt = salt or secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), 120000)
    return f"{salt}${digest.hex()}"


def verify_password(password, stored):
    try:
        salt, digest = stored.split("$", 1)
    except ValueError:
        return False
    return hmac.compare_digest(hash_password(password, salt), stored)


def row_to_dict(row):
    return dict(row) if row else None


def public_user(row):
    if not row:
        return None
    user = dict(row)
    user.pop("password_hash", None)
    return user


def load_seed_products():
    if not os.path.exists(PRODUCTS_JSON_PATH):
        return []
    with open(PRODUCTS_JSON_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, list):
        raise ValueError("products.json must contain a list")
    products = []
    for item in data:
        if not isinstance(item, dict):
            continue
        products.append(
            (
                item.get("name", "").strip(),
                item.get("category", "工作室選品").strip() or "工作室選品",
                item.get("description", "").strip(),
                int(item.get("price", 0)),
                int(item.get("stock", 0)),
                item.get("status", "draft"),
                1 if item.get("featured") else 0,
            )
        )
    return products


def ensure_default_admin(con):
    admin = con.execute(
        """
        SELECT id
        FROM users
        WHERE username = ? OR email = ? OR (role = 'admin' AND status = 'approved')
        ORDER BY id ASC
        LIMIT 1
        """,
        (DEFAULT_ADMIN_USERNAME, DEFAULT_ADMIN_EMAIL),
    ).fetchone()
    values = (
        DEFAULT_ADMIN_USERNAME,
        DEFAULT_ADMIN_EMAIL,
        hash_password(DEFAULT_ADMIN_PASSWORD),
    )
    if admin:
        con.execute(
            """
            UPDATE users
            SET username = ?, email = ?, password_hash = ?, role = 'admin', status = 'approved'
            WHERE id = ?
            """,
            (*values, admin["id"]),
        )
    else:
        con.execute(
            """
            INSERT INTO users (username, email, password_hash, role, status)
            VALUES (?, ?, ?, 'admin', 'approved')
            """,
            values,
        )


def init_db():
    os.makedirs(DATA_DIR, exist_ok=True)
    with db() as con:
        con.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL UNIQUE,
                email TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                role TEXT NOT NULL DEFAULT 'member',
                status TEXT NOT NULL DEFAULT 'pending',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS sessions (
                token TEXT PRIMARY KEY,
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                expires_at INTEGER NOT NULL
            );

            CREATE TABLE IF NOT EXISTS products (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                category TEXT NOT NULL DEFAULT '工作室選品',
                description TEXT NOT NULL DEFAULT '',
                price INTEGER NOT NULL,
                stock INTEGER NOT NULL DEFAULT 0,
                status TEXT NOT NULL DEFAULT 'draft',
                featured INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS orders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL REFERENCES users(id),
                customer_name TEXT NOT NULL,
                phone TEXT NOT NULL,
                address TEXT NOT NULL,
                note TEXT NOT NULL DEFAULT '',
                total INTEGER NOT NULL,
                status TEXT NOT NULL DEFAULT 'new',
                review_status TEXT NOT NULL DEFAULT 'pending',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS order_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                order_id INTEGER NOT NULL REFERENCES orders(id) ON DELETE CASCADE,
                product_id INTEGER NOT NULL REFERENCES products(id),
                product_name TEXT NOT NULL,
                quantity INTEGER NOT NULL,
                unit_price INTEGER NOT NULL,
                subtotal INTEGER NOT NULL
            );

            CREATE TABLE IF NOT EXISTS site_stats (
                key TEXT PRIMARY KEY,
                value INTEGER NOT NULL DEFAULT 0,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            """
        )

        order_columns = {
            row["name"]
            for row in con.execute("PRAGMA table_info(orders)").fetchall()
        }
        if "review_status" not in order_columns:
            con.execute("ALTER TABLE orders ADD COLUMN review_status TEXT NOT NULL DEFAULT 'pending'")

        ensure_default_admin(con)

        product_count = con.execute("SELECT COUNT(*) AS c FROM products").fetchone()["c"]
        order_count = con.execute("SELECT COUNT(*) AS c FROM orders").fetchone()["c"]
        order_item_count = con.execute("SELECT COUNT(*) AS c FROM order_items").fetchone()["c"]
        seed_products = load_seed_products()
        if seed_products and (product_count == 0 or (product_count == 3 and order_count == 0 and order_item_count == 0)):
            con.execute("DELETE FROM products")
            con.executemany(
                """
                INSERT INTO products
                (name, category, description, price, stock, status, featured)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                seed_products,
            )


class App(BaseHTTPRequestHandler):
    server_version = "StudioShop/1.0"
    protocol_version = "HTTP/1.1"
    _suppress_body = False

    def handle_one_request(self):
        try:
            return super().handle_one_request()
        except Exception:
            traceback.print_exc()
            try:
                body = json.dumps({"ok": False, "error": "伺服器發生錯誤"}, ensure_ascii=False).encode("utf-8")
                self.send_response(500)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Connection", "close")
                self.end_headers()
                self.write_body(body)
            except Exception:
                pass
            return None

    def write_body(self, content):
        if not self._suppress_body and content:
            self.wfile.write(content)

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == "/":
            return self.serve_index()
        if parsed.path.startswith("/static/"):
            name = unquote(parsed.path.replace("/static/", "", 1))
            if ".." in name or name.startswith("/"):
                return self.error(400, "路徑無效")
            path = os.path.join(STATIC_DIR, name)
            content_type = "text/plain"
            if name.endswith(".css"):
                content_type = "text/css; charset=utf-8"
            elif name.endswith(".js"):
                content_type = "application/javascript; charset=utf-8"
            elif name.lower().endswith(".png"):
                content_type = "image/png"
            elif name.lower().endswith((".jpg", ".jpeg")):
                content_type = "image/jpeg"
            elif name.lower().endswith(".gif"):
                content_type = "image/gif"
            elif name.lower().endswith(".webp"):
                content_type = "image/webp"
            return self.serve_file(path, content_type)
        if parsed.path.startswith("/image/"):
            name = unquote(parsed.path.replace("/image/", "", 1))
            if ".." in name or name.startswith("/"):
                return self.error(400, "路徑無效")
            path = os.path.join(BASE_DIR, "image", name)
            content_type = "application/octet-stream"
            lowered = name.lower()
            if lowered.endswith(".png"):
                content_type = "image/png"
            elif lowered.endswith((".jpg", ".jpeg")):
                content_type = "image/jpeg"
            elif lowered.endswith(".gif"):
                content_type = "image/gif"
            elif lowered.endswith(".webp"):
                content_type = "image/webp"
            return self.serve_file(path, content_type)
        if parsed.path.startswith("/api/"):
            return self.handle_api("GET", parsed.path, parse_qs(parsed.query))
        return self.error(404, "找不到資源")

    def do_HEAD(self):
        self._suppress_body = True
        try:
            return self.do_GET()
        finally:
            self._suppress_body = False

    def do_POST(self):
        parsed = urlparse(self.path)
        if parsed.path.startswith("/api/"):
            return self.handle_api("POST", parsed.path, {})
        return self.error(404, "找不到資源")

    def do_PUT(self):
        parsed = urlparse(self.path)
        if parsed.path.startswith("/api/"):
            return self.handle_api("PUT", parsed.path, {})
        return self.error(404, "找不到資源")

    def do_DELETE(self):
        parsed = urlparse(self.path)
        if parsed.path.startswith("/api/"):
            return self.handle_api("DELETE", parsed.path, {})
        return self.error(404, "找不到資源")

    def serve_file(self, path, content_type):
        if not os.path.exists(path):
            return self.error(404, "找不到資源")
        with open(path, "rb") as f:
            content = f.read()
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(content)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.write_body(content)

    def serve_index(self):
        path = os.path.join(BASE_DIR, "index.html")
        if os.path.exists(path):
            try:
                if self.command == "GET":
                    self.record_home_visit()
                with open(path, "r", encoding="utf-8") as f:
                    html = f.read()
                image_path = os.path.join(BASE_DIR, "static", "vios.png")
                if os.path.exists(image_path):
                    with open(image_path, "rb") as f:
                        image_data = base64.b64encode(f.read()).decode("ascii")
                    image_url = f"data:image/png;base64,{image_data}"
                else:
                    image_url = "data:image/svg+xml;charset=UTF-8,<svg xmlns='http://www.w3.org/2000/svg' width='900' height='675'><rect width='100%25' height='100%25' fill='%23d8d2c8'/></svg>"
                script = f"<script>window.DEFAULT_PRODUCT_IMAGE={json.dumps(image_url, ensure_ascii=False)};</script>"
                if "</head>" in html:
                    html = html.replace("</head>", f"{script}</head>", 1)
                else:
                    html = f"{script}{html}"
                content = html.encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(content)))
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self.write_body(content)
                return
            except Exception:
                traceback.print_exc()
        fallback = """<!doctype html><html lang=\"zh-Hant\"><head><meta charset=\"utf-8\"><meta name=\"viewport\" content=\"width=device-width, initial-scale=1\"><title>傑生工程工作室</title></head><body><h1>傑生工程工作室</h1><p>伺服器已啟動。</p></body></html>""".encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(fallback)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.write_body(fallback)

    def record_home_visit(self):
        with db() as con:
            con.execute(
                """
                INSERT INTO site_stats (key, value)
                VALUES ('home_visits', 1)
                ON CONFLICT(key) DO UPDATE SET
                    value = value + 1,
                    updated_at = CURRENT_TIMESTAMP
                """
            )

    def visit_stats(self):
        with db() as con:
            row = con.execute(
                "SELECT value, updated_at FROM site_stats WHERE key = 'home_visits'"
            ).fetchone()
        return self.json(
            {
                "ok": True,
                "visits": int(row["value"]) if row else 0,
                "updated_at": row["updated_at"] if row else None,
            }
        )

    def read_json(self):
        length = int(self.headers.get("Content-Length", 0))
        if length == 0:
            return {}
        try:
            return json.loads(self.rfile.read(length).decode("utf-8"))
        except json.JSONDecodeError:
            raise ValueError("JSON 格式不正確")

    def json(self, payload, status=200):
        content = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(content)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.write_body(content)

    def error(self, status, message):
        return self.json({"ok": False, "error": message}, status)

    def current_user(self):
        cookie = self.headers.get("Cookie", "")
        token = ""
        for part in cookie.split(";"):
            if part.strip().startswith("studio_session="):
                token = part.strip().split("=", 1)[1]
                break
        if not token:
            return None
        now = int(time.time())
        with db() as con:
            row = con.execute(
                """
                SELECT users.id, username, email, role, status, created_at
                FROM sessions
                JOIN users ON users.id = sessions.user_id
                WHERE token = ? AND expires_at > ?
                """,
                (token, now),
            ).fetchone()
        return row_to_dict(row)

    def require_user(self):
        user = self.current_user()
        if not user:
            self.error(401, "請先登入")
            return None
        if user["status"] != "approved":
            self.error(403, "會員尚未通過審核")
            return None
        return user

    def require_admin(self):
        user = self.require_user()
        if not user:
            return None
        if user["role"] != "admin":
            self.error(403, "需要管理員權限")
            return None
        return user

    def handle_api(self, method, path, query):
        try:
            if path == "/api/me" and method == "GET":
                return self.json({"ok": True, "user": self.current_user()})
            if path == "/api/visit-stats" and method == "GET":
                return self.visit_stats()
            if path == "/api/register" and method == "POST":
                return self.register()
            if path == "/api/login" and method == "POST":
                return self.login()
            if path == "/api/logout" and method == "POST":
                return self.logout()
            if path == "/api/products" and method == "GET":
                return self.list_products(query)
            if path == "/api/products" and method == "POST":
                return self.create_product()
            if path.startswith("/api/products/") and method == "PUT":
                return self.update_product(int(path.rsplit("/", 1)[1]))
            if path.startswith("/api/products/") and method == "DELETE":
                return self.delete_product(int(path.rsplit("/", 1)[1]))
            if path == "/api/users" and method == "GET":
                return self.list_users()
            if path.startswith("/api/users/") and method == "PUT":
                return self.update_user(int(path.rsplit("/", 1)[1]))
            if path.startswith("/api/users/") and method == "DELETE":
                return self.delete_user(int(path.rsplit("/", 1)[1]))
            if path == "/api/orders" and method == "GET":
                return self.list_orders()
            if path == "/api/orders" and method == "POST":
                return self.create_order()
            if path.startswith("/api/orders/") and method == "PUT":
                return self.update_order(int(path.rsplit("/", 1)[1]))
            if path.startswith("/api/orders/") and method == "DELETE":
                return self.delete_order(int(path.rsplit("/", 1)[1]))
            return self.error(404, "API 不存在")
        except ValueError as exc:
            return self.error(400, str(exc))
        except sqlite3.IntegrityError:
            return self.error(409, "帳號、Email 或資料已存在")
        except Exception as exc:
            return self.error(500, f"伺服器錯誤：{exc}")

    def register(self):
        data = self.read_json()
        username = data.get("username", "").strip()
        email = data.get("email", "").strip()
        password = data.get("password", "")
        if len(username) < 3 or "@" not in email or len(password) < 6:
            raise ValueError("請輸入至少 3 字元帳號、正確 Email，以及至少 6 字元密碼")
        with db() as con:
            con.execute(
                "INSERT INTO users (username, email, password_hash) VALUES (?, ?, ?)",
                (username, email, hash_password(password)),
            )
        return self.json({"ok": True, "message": "申請成功"})

    def login(self):
        data = self.read_json()
        username = data.get("username", "").strip()
        password = data.get("password", "")
        with db() as con:
            user = con.execute("SELECT * FROM users WHERE username = ? OR email = ?", (username, username)).fetchone()
            if not user or not verify_password(password, user["password_hash"]):
                return self.error(401, "帳號或密碼錯誤")
            token = secrets.token_urlsafe(32)
            con.execute(
                "INSERT INTO sessions (token, user_id, expires_at) VALUES (?, ?, ?)",
                (token, user["id"], int(time.time()) + SESSION_TTL),
            )
        cookie = f"studio_session={token}; HttpOnly; SameSite=Lax; Path=/; Max-Age={SESSION_TTL}"
        body = json.dumps({"ok": True, "user": public_user(user)}, ensure_ascii=False).encode("utf-8")
        self.send_response(200)
        self.send_header("Set-Cookie", cookie)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.write_body(body)

    def logout(self):
        cookie = self.headers.get("Cookie", "")
        token = ""
        for part in cookie.split(";"):
            if part.strip().startswith("studio_session="):
                token = part.strip().split("=", 1)[1]
        with db() as con:
            if token:
                con.execute("DELETE FROM sessions WHERE token = ?", (token,))
        body = b'{"ok": true}'
        self.send_response(200)
        self.send_header("Set-Cookie", "studio_session=; HttpOnly; SameSite=Lax; Path=/; Max-Age=0")
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.write_body(body)

    def list_products(self, query):
        admin = query.get("admin", ["0"])[0] == "1"
        if admin and not self.require_admin():
            return
        sql = "SELECT * FROM products"
        params = []
        if not admin:
            sql += " WHERE status = 'active'"
        sql += " ORDER BY featured DESC, created_at DESC"
        with db() as con:
            products = [dict(row) for row in con.execute(sql, params).fetchall()]
        return self.json({"ok": True, "products": products})

    def create_product(self):
        if not self.require_admin():
            return
        data = self.product_payload()
        with db() as con:
            cur = con.execute(
                """
                INSERT INTO products (name, category, description, price, stock, status, featured)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                data,
            )
        return self.json({"ok": True, "id": cur.lastrowid})

    def update_product(self, product_id):
        if not self.require_admin():
            return
        data = self.product_payload()
        with db() as con:
            con.execute(
                """
                UPDATE products
                SET name = ?, category = ?, description = ?, price = ?, stock = ?,
                    status = ?, featured = ?, updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (*data, product_id),
            )
        return self.json({"ok": True})

    def delete_product(self, product_id):
        if not self.require_admin():
            return
        with db() as con:
            used = con.execute("SELECT id FROM order_items WHERE product_id = ? LIMIT 1", (product_id,)).fetchone()
            if used:
                con.execute(
                    "UPDATE products SET status = 'archived', updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                    (product_id,),
                )
            else:
                con.execute("DELETE FROM products WHERE id = ?", (product_id,))
        return self.json({"ok": True})

    def product_payload(self):
        data = self.read_json()
        name = data.get("name", "").strip()
        category = data.get("category", "工作室選品").strip() or "工作室選品"
        description = data.get("description", "").strip()
        status = data.get("status", "draft")
        if status not in {"draft", "active", "archived"}:
            raise ValueError("商品狀態不正確")
        try:
            price = int(data.get("price", 0))
            stock = int(data.get("stock", 0))
            featured = 1 if data.get("featured") else 0
        except (TypeError, ValueError):
            raise ValueError("價格與庫存需為數字")
        if not name or price < 0 or stock < 0:
            raise ValueError("請輸入商品名稱，價格與庫存不可小於 0")
        return (name, category, description, price, stock, status, featured)

    def list_users(self):
        if not self.require_admin():
            return
        with db() as con:
            users = [
                dict(row)
                for row in con.execute(
                    "SELECT id, username, email, role, status, created_at FROM users ORDER BY created_at DESC"
                ).fetchall()
            ]
        return self.json({"ok": True, "users": users})

    def update_user(self, user_id):
        admin = self.require_admin()
        if not admin:
            return
        data = self.read_json()
        status = data.get("status")
        role = data.get("role")
        if status not in {"pending", "approved", "rejected"} or role not in {"member", "admin"}:
            raise ValueError("會員狀態或角色不正確")
        if user_id == admin["id"] and (status != "approved" or role != "admin"):
            raise ValueError("不能移除目前登入管理員的管理權限")
        with db() as con:
            con.execute("UPDATE users SET status = ?, role = ? WHERE id = ?", (status, role, user_id))
        return self.json({"ok": True})

    def delete_user(self, user_id):
        admin = self.require_admin()
        if not admin:
            return
        if user_id == admin["id"]:
            raise ValueError("不能刪除目前登入的管理員帳號")
        with db() as con:
            target = con.execute("SELECT id FROM users WHERE id = ?", (user_id,)).fetchone()
            if not target:
                raise ValueError("找不到會員資料")
            pending_count = con.execute(
                "SELECT COUNT(*) AS c FROM orders WHERE user_id = ? AND review_status = 'pending'",
                (user_id,),
            ).fetchone()["c"]
            if pending_count:
                raise ValueError("此會員仍有待審核訂單，無法刪除")
            reviewed_orders = con.execute(
                "SELECT id FROM orders WHERE user_id = ? AND review_status != 'pending'",
                (user_id,),
            ).fetchall()
            for order in reviewed_orders:
                self._delete_order_rows(con, order["id"])
            con.execute("DELETE FROM users WHERE id = ?", (user_id,))
        return self.json({"ok": True})

    def list_orders(self):
        user = self.require_user()
        if not user:
            return
        with db() as con:
            if user["role"] == "admin":
                rows = con.execute(
                    """
                    SELECT orders.*, users.username
                    FROM orders JOIN users ON users.id = orders.user_id
                    ORDER BY orders.created_at DESC
                    """
                ).fetchall()
            else:
                rows = con.execute(
                    "SELECT orders.*, ? AS username FROM orders WHERE user_id = ? ORDER BY created_at DESC",
                    (user["username"], user["id"]),
                ).fetchall()
            orders = []
            for row in rows:
                order = dict(row)
                order["items"] = [
                    dict(item)
                    for item in con.execute(
                        "SELECT product_name, quantity, unit_price, subtotal FROM order_items WHERE order_id = ?",
                        (order["id"],),
                    ).fetchall()
                ]
                orders.append(order)
        return self.json({"ok": True, "orders": orders})

    def create_order(self):
        user = self.require_user()
        if not user:
            return
        data = self.read_json()
        items = data.get("items", [])
        customer_name = data.get("customer_name", "").strip()
        phone = data.get("phone", "").strip()
        address = data.get("address", "").strip()
        note = data.get("note", "").strip()
        if not items or not customer_name or not phone or not address:
            raise ValueError("請填寫收件資料並選擇商品")
        with db() as con:
            total = 0
            order_items = []
            for item in items:
                product_id = int(item.get("product_id", 0))
                quantity = int(item.get("quantity", 0))
                if quantity <= 0:
                    raise ValueError("商品數量需大於 0")
                product = con.execute("SELECT * FROM products WHERE id = ? AND status = 'active'", (product_id,)).fetchone()
                if not product:
                    raise ValueError("商品不存在或尚未上架")
                if product["stock"] < quantity:
                    raise ValueError(f"{product['name']} 庫存不足")
                subtotal = product["price"] * quantity
                total += subtotal
                order_items.append((product, quantity, subtotal))

            cur = con.execute(
                """
                INSERT INTO orders (user_id, customer_name, phone, address, note, total, review_status)
                VALUES (?, ?, ?, ?, ?, ?, 'pending')
                """,
                (user["id"], customer_name, phone, address, note, total),
            )
            order_id = cur.lastrowid
            for product, quantity, subtotal in order_items:
                con.execute(
                    """
                    INSERT INTO order_items (order_id, product_id, product_name, quantity, unit_price, subtotal)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (order_id, product["id"], product["name"], quantity, product["price"], subtotal),
                )
                con.execute("UPDATE products SET stock = stock - ? WHERE id = ?", (quantity, product["id"]))
        return self.json({"ok": True, "order_id": order_id})

    def update_order(self, order_id):
        if not self.require_admin():
            return
        data = self.read_json()
        status = data.get("status")
        review_status = data.get("review_status")
        if status is not None and status not in {"new", "paid", "processing", "shipped", "completed", "cancelled"}:
            raise ValueError("訂單狀態不正確")
        if review_status is not None and review_status not in ORDER_REVIEW_STATUSES:
            raise ValueError("審核狀態不正確")
        if status is None and review_status is None:
            raise ValueError("請提供更新內容")
        with db() as con:
            if status is not None:
                con.execute("UPDATE orders SET status = ? WHERE id = ?", (status, order_id))
            if review_status is not None:
                con.execute("UPDATE orders SET review_status = ? WHERE id = ?", (review_status, order_id))
        return self.json({"ok": True})

    def _delete_order_rows(self, con, order_id):
        order = con.execute("SELECT id, review_status FROM orders WHERE id = ?", (order_id,)).fetchone()
        if not order:
            raise ValueError("找不到訂單資料")
        if order["review_status"] == "pending":
            raise ValueError("只有已審核的訂單可以刪除")
        items = con.execute(
            "SELECT product_id, quantity FROM order_items WHERE order_id = ?",
            (order_id,),
        ).fetchall()
        for item in items:
            con.execute(
                "UPDATE products SET stock = stock + ? WHERE id = ?",
                (item["quantity"], item["product_id"]),
            )
        con.execute("DELETE FROM orders WHERE id = ?", (order_id,))

    def delete_order(self, order_id):
        if not self.require_admin():
            return
        with db() as con:
            self._delete_order_rows(con, order_id)
        return self.json({"ok": True})


def main():
    init_db()
    host = os.environ.get("HOST", "0.0.0.0")
    port = int(os.environ.get("PORT", "8013"))
    httpd = ThreadingHTTPServer((host, port), App)
    browser_host = "localhost" if host in {"0.0.0.0", "::"} else host
    print(f"Studio shop running at http://{browser_host}:{port}/")
    httpd.serve_forever()


if __name__ == "__main__":
    main()

