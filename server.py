import base64
import html
import smtplib
import urllib.request
from datetime import datetime
from email.message import EmailMessage
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, quote_plus, urlparse, unquote
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
ECPAY_STAGE_URL = "https://payment-stage.ecpay.com.tw/Cashier/AioCheckOut/V5"
ECPAY_PRODUCTION_URL = "https://payment.ecpay.com.tw/Cashier/AioCheckOut/V5"
# 綠界官方公開測試特店編號；只用於避免誤把測試帳號送往正式 API。
ECPAY_TEST_MERCHANT_IDS = frozenset({"2000132", "2000214", "2000933", "3002607"})
MAIL_LOG_PATH = os.path.join(BASE_DIR, "mail.log")
NOTE_PRODUCT = (
    "傑生工程筆記本",
    "筆記本",
    (
        "整理 ChatGPT、Copilot、Codex 與 Git/GitHub 的實戰重點，適合初學者快速上手 AI 開發與版本控制。"
    ),
    600,
    30,
    "active",
    1,
    "/static/精華筆記V1(預覽).pdf",
    "/image/notebook/未命名.jpg",
)
AT1_DESCRIPTION = (
    "AT1 聲控平台結合 Arduino、藍牙、語音控制與接近感應技術，帶你快速完成專題製作與智慧控制應用。"
    "內含完整程式、電路教學與實作範例，適合學生學習、DIY 愛好者及求職作品製作。"
)
AT1_PRODUCTS = (
    (
        "AT1筆記本(精華筆記)",
        "筆記本",
        AT1_DESCRIPTION,
        400,
        30,
        "active",
        1,
        "/static/XAT1 上架資料.pdf",
        "/image/AT1/未命名.png",
    ),
    (
        "AT1 硬體 包含 AT1筆記本",
        "硬體",
        AT1_DESCRIPTION,
        1300,
        30,
        "active",
        1,
        "",
        "/image/AT1/未命名.png",
    ),
)


def log_notification_error(message):
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
    try:
        with open(MAIL_LOG_PATH, "a", encoding="utf-8") as f:
            f.write(f"[{timestamp}] {message}\n")
    except Exception:
        traceback.print_exc()


def _clean_webhook_url(url):
    url = (url or "").strip()
    if not url:
        return ""
    # 如果不小心把瀏覽器看到的 JSON 貼進 Render，這裡會自動取出 url 欄位。
    if url.startswith("{"):
        try:
            data = json.loads(url)
            url = str(data.get("url", "")).strip()
        except Exception:
            pass
    return url


def send_discord_member_apply_notification(*, name, email, phone, account, created_at):
    webhook_url = _clean_webhook_url(os.getenv("DISCORD_WEBHOOK_URL"))
    if not webhook_url:
        raise RuntimeError("DISCORD_WEBHOOK_URL 未設定")

    payload = {
        "content": (
            "🔔 **有新的會員申請**\n"
            f"姓名：{name}\n"
            f"Email：{email}\n"
            f"電話：{phone}\n"
            f"帳號：{account}\n"
            f"申請時間：{created_at}"
        )
    }
    req = urllib.request.Request(
        webhook_url,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        method="POST",
        headers={
            "Content-Type": "application/json",
            "User-Agent": "Mozilla/5.0",
        },
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        return resp.status


def mail_settings():
    return {
        "server": os.getenv("MAIL_SERVER", "smtp.gmail.com"),
        "port": int(os.getenv("MAIL_PORT", "587")),
        "use_tls": os.getenv("MAIL_USE_TLS", "True").lower() in {"1", "true", "yes", "on"},
        "username": os.getenv("MAIL_USERNAME") or os.getenv("EMAIL_USER"),
        "password": os.getenv("MAIL_PASSWORD") or os.getenv("EMAIL_PASSWORD"),
        "to": os.getenv("ADMIN_EMAIL") or os.getenv("MAIL_TO") or os.getenv("MAIL_USERNAME") or os.getenv("EMAIL_USER"),
    }


def send_gmail_member_apply_notification(*, name, email, phone, account, created_at):
    settings = mail_settings()
    if not settings["username"] or not settings["password"] or not settings["to"]:
        raise RuntimeError("Gmail SMTP 環境變數未完整設定")

    message = EmailMessage()
    message["Subject"] = "【會員網站】有新的會員申請"
    message["From"] = settings["username"]
    message["To"] = settings["to"]
    message.set_content(
        "\n".join(
            [
                "有新的會員申請：",
                f"姓名：{name}",
                f"Email：{email}",
                f"電話：{phone}",
                f"帳號：{account}",
                f"申請時間：{created_at}",
            ]
        )
    )

    with smtplib.SMTP(settings["server"], settings["port"], timeout=15) as smtp:
        smtp.ehlo()
        if settings["use_tls"]:
            smtp.starttls()
            smtp.ehlo()
        smtp.login(settings["username"], settings["password"])
        smtp.send_message(message)


def notify_member_apply(*, name, email, phone, account, created_at):
    # Discord 優先；Gmail 保留。任何通知失敗都不影響其他流程。
    try:
        send_discord_member_apply_notification(
            name=name, email=email, phone=phone, account=account, created_at=created_at
        )
        print("Discord 會員申請通知已送出")
    except Exception as exc:
        log_notification_error(f"Discord通知失敗 {type(exc).__name__}: {exc}")
        traceback.print_exc()

    try:
        send_gmail_member_apply_notification(
            name=name, email=email, phone=phone, account=account, created_at=created_at
        )
        print("Gmail 會員申請通知已送出")
    except Exception as exc:
        log_notification_error(f"Gmail通知失敗 {type(exc).__name__}: {exc}")
        traceback.print_exc()



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


def ecpay_settings(require_enabled=True):
    environment = os.getenv("ECPAY_ENV", "stage").strip().lower()
    if environment not in {"stage", "production"}:
        raise ValueError("ECPAY_ENV 必須是 stage 或 production")
    enabled = os.getenv("ECPAY_ENABLED", "true").strip().lower() in {"1", "true", "yes", "on"}
    if require_enabled and not enabled:
        raise ValueError("綠界信用卡付款目前已停用")
    settings = {
        "enabled": enabled,
        "merchant_id": os.getenv("ECPAY_MERCHANT_ID", "").strip(),
        "hash_key": os.getenv("ECPAY_HASH_KEY", "").strip(),
        "hash_iv": os.getenv("ECPAY_HASH_IV", "").strip(),
        "environment": environment,
        "return_url": os.getenv("ECPAY_RETURN_URL", "").strip(),
        "order_result_url": os.getenv("ECPAY_ORDER_RESULT_URL", "").strip(),
        "checkout_url": ECPAY_PRODUCTION_URL if environment == "production" else ECPAY_STAGE_URL,
    }
    missing = [
        name
        for name, value in (
            ("ECPAY_MERCHANT_ID", settings["merchant_id"]),
            ("ECPAY_HASH_KEY", settings["hash_key"]),
            ("ECPAY_HASH_IV", settings["hash_iv"]),
            ("ECPAY_RETURN_URL", settings["return_url"]),
            ("ECPAY_ORDER_RESULT_URL", settings["order_result_url"]),
        )
        if not value
    ]
    if missing:
        raise ValueError(f"尚未設定綠界環境變數：{', '.join(missing)}")
    if (
        len(settings["merchant_id"]) > 10
        or not settings["merchant_id"].isascii()
        or not settings["merchant_id"].isalnum()
    ):
        raise ValueError("ECPAY_MERCHANT_ID 格式不正確")
    if settings["return_url"] == settings["order_result_url"]:
        raise ValueError("ECPAY_RETURN_URL 與 ECPAY_ORDER_RESULT_URL 不可相同")
    for name, value in (
        ("ECPAY_RETURN_URL", settings["return_url"]),
        ("ECPAY_ORDER_RESULT_URL", settings["order_result_url"]),
    ):
        if not value.lower().startswith("https://"):
            raise ValueError(f"{name} 必須使用 HTTPS")
        if len(value) > 200:
            raise ValueError(f"{name} 不可超過 200 字元")
    if environment == "production" and settings["merchant_id"] in ECPAY_TEST_MERCHANT_IDS:
        raise ValueError("正式環境不可使用綠界測試特店編號")
    return settings


def ecpay_check_mac_value(parameters, hash_key, hash_iv):
    """依綠界 AioCheckOut 規範產生 SHA256 CheckMacValue。"""
    values = {
        str(key): str(value)
        for key, value in parameters.items()
        if key.lower() != "checkmacvalue" and value is not None
    }
    query = "&".join(f"{key}={values[key]}" for key in sorted(values, key=str.lower))
    encoded = quote_plus(f"HashKey={hash_key}&{query}&HashIV={hash_iv}", safe="-_.!*()")
    encoded = encoded.replace("~", "%7E").lower()
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest().upper()


def ecpay_verify_check_mac(parameters, hash_key, hash_iv):
    received = str(parameters.get("CheckMacValue", ""))
    if not received:
        return False
    expected = ecpay_check_mac_value(parameters, hash_key, hash_iv)
    return hmac.compare_digest(received.upper(), expected.upper())


def sanitize_ecpay_item_name(name):
    cleaned = "".join(ch if ch.isalnum() or ch in " -_()[]" else " " for ch in str(name))
    return " ".join(cleaned.split()) or "商品"


def build_ecpay_item_name(items):
    parts = [
        f"{sanitize_ecpay_item_name(item['product_name'])} x {item['quantity']}"
        for item in items
    ]
    return "#".join(parts)[:400]


def generate_merchant_trade_no():
    # 綠界限制 20 碼英數；時間加亂數兼顧可讀性與唯一性。
    return f"J{int(time.time()):010d}{secrets.token_hex(4).upper()}"[:20]


def safe_payment_response(parameters):
    allowed = {
        "MerchantID",
        "MerchantTradeNo",
        "RtnCode",
        "RtnMsg",
        "TradeNo",
        "TradeAmt",
        "PaymentDate",
        "PaymentType",
        "PaymentTypeChargeFee",
        "SimulatePaid",
    }
    return json.dumps(
        {key: str(parameters[key])[:500] for key in allowed if key in parameters},
        ensure_ascii=False,
        sort_keys=True,
    )


def public_user(row):
    if not row:
        return None
    user = dict(row)
    user.pop("password_hash", None)
    return user


def default_admin_credentials_match(username, password):
    return username in {DEFAULT_ADMIN_USERNAME, DEFAULT_ADMIN_EMAIL} and password == DEFAULT_ADMIN_PASSWORD


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
                item.get("preview_url", "").strip(),
                item.get("image_url", "").strip(),
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
                preview_url TEXT NOT NULL DEFAULT '',
                image_url TEXT NOT NULL DEFAULT '',
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
        payment_columns = (
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
            # 舊流程原本在建單時扣庫存，因此既存訂單 migration 預設為 1。
            ("inventory_deducted", "INTEGER NOT NULL DEFAULT 1"),
            ("updated_at", "TEXT"),
        )
        for column_name, definition in payment_columns:
            if column_name not in order_columns:
                con.execute(f"ALTER TABLE orders ADD COLUMN {column_name} {definition}")
        con.execute("UPDATE orders SET updated_at = COALESCE(updated_at, created_at, CURRENT_TIMESTAMP)")
        con.execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS idx_orders_merchant_trade_no
            ON orders(merchant_trade_no)
            WHERE merchant_trade_no IS NOT NULL
            """
        )
        con.execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS idx_orders_checkout_token
            ON orders(checkout_token)
            WHERE checkout_token IS NOT NULL
            """
        )
        product_columns = {
            row["name"]
            for row in con.execute("PRAGMA table_info(products)").fetchall()
        }
        if "preview_url" not in product_columns:
            con.execute("ALTER TABLE products ADD COLUMN preview_url TEXT NOT NULL DEFAULT ''")
        if "image_url" not in product_columns:
            con.execute("ALTER TABLE products ADD COLUMN image_url TEXT NOT NULL DEFAULT ''")

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
                (name, category, description, price, stock, status, featured, preview_url, image_url)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                seed_products,
            )

        note_exists = con.execute(
            "SELECT id FROM products WHERE name = ? LIMIT 1",
            (NOTE_PRODUCT[0],),
        ).fetchone()
        if not note_exists:
            con.execute(
                """
                INSERT INTO products
                (name, category, description, price, stock, status, featured, preview_url, image_url)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                NOTE_PRODUCT,
            )
        else:
            con.execute(
                """
                UPDATE products
                SET name = ?, category = ?, description = ?, price = ?, stock = ?, status = ?, featured = ?,
                    preview_url = ?, image_url = ?, updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (*NOTE_PRODUCT, note_exists["id"]),
            )

        con.execute(
            "UPDATE products SET name = ? WHERE name IN (?, ?)",
            (
                "AT1筆記本(精華筆記)",
                "AT1筆記本（偉客多工作室出版）",
                "AT1 筆記本（偉客多工作室出版）",
            ),
        )
        con.execute(
            "UPDATE products SET name = ? WHERE name IN (?, ?)",
            ("AT1 硬體 包含 AT1筆記本", "AT1硬體", "AT1 硬體"),
        )

        for product in AT1_PRODUCTS:
            product_exists = con.execute(
                "SELECT id FROM products WHERE name = ? LIMIT 1",
                (product[0],),
            ).fetchone()
            if not product_exists:
                con.execute(
                    """
                    INSERT INTO products
                    (name, category, description, price, stock, status, featured, preview_url, image_url)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    product,
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
        if parsed.path == "/ecpay/result":
            return self.ecpay_result({})
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
            elif name.lower().endswith(".pdf"):
                content_type = "application/pdf"
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
        if parsed.path == "/ecpay/return":
            return self.ecpay_return()
        if parsed.path == "/ecpay/result":
            return self.ecpay_result(self.read_form())
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

    def read_form(self):
        length = int(self.headers.get("Content-Length", 0))
        if length <= 0:
            return {}
        raw = self.rfile.read(length).decode("utf-8", errors="replace")
        return {key: values[-1] for key, values in parse_qs(raw, keep_blank_values=True).items()}

    def text(self, value, status=200, content_type="text/plain; charset=utf-8"):
        content = value.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(content)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.write_body(content)

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
            if path == "/api/ecpay/checkout" and method == "POST":
                return self.create_ecpay_checkout()
            if path == "/api/ecpay/status" and method == "GET":
                return self.ecpay_status(query)
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

    def login(self):
        data = self.read_json()
        username = data.get("username", "").strip()
        password = data.get("password", "")
        if not default_admin_credentials_match(username, password):
            return self.error(401, "帳號或密碼錯誤")
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
                INSERT INTO products (name, category, description, price, stock, status, featured, preview_url, image_url)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                    status = ?, featured = ?, preview_url = ?, image_url = ?, updated_at = CURRENT_TIMESTAMP
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
        preview_url = data.get("preview_url", "").strip()
        image_url = data.get("image_url", "").strip()
        return (name, category, description, price, stock, status, featured, preview_url, image_url)

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
        if not self.require_admin():
            return
        with db() as con:
            rows = con.execute(
                """
                SELECT orders.*, COALESCE(users.username, '訪客') AS username
                FROM orders
                LEFT JOIN users ON users.id = orders.user_id
                ORDER BY orders.created_at DESC
                """
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
        data = self.read_json()
        items = data.get("items", [])
        customer_name = data.get("customer_name", "").strip()
        phone = data.get("phone", "").strip()
        address = data.get("address", "").strip()
        note = data.get("note", "").strip()
        if not items or not customer_name or not phone or not address:
            raise ValueError("請填寫收件資料並選擇商品")
        with db() as con:
            admin = con.execute(
                "SELECT id FROM users WHERE username = ? OR email = ? ORDER BY id ASC LIMIT 1",
                (DEFAULT_ADMIN_USERNAME, DEFAULT_ADMIN_EMAIL),
            ).fetchone()
            if not admin:
                raise ValueError("管理員帳號不存在")
            user = self.current_user()
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

            user_id = admin["id"]
            if user and user.get("role") == "admin" and user.get("status") == "approved":
                user_id = user["id"]

            cur = con.execute(
                """
                INSERT INTO orders
                (user_id, customer_name, phone, address, note, total, review_status,
                 payment_method, payment_status, payment_amount, inventory_deducted)
                VALUES (?, ?, ?, ?, ?, ?, 'pending', 'manual', 'pending', ?, 1)
                """,
                (user_id, customer_name, phone, address, note, total, total),
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

    def create_ecpay_checkout(self):
        settings = ecpay_settings()
        data = self.read_json()
        items = data.get("items", [])
        customer_name = data.get("customer_name", "").strip()
        phone = data.get("phone", "").strip()
        address = data.get("address", "").strip()
        note = data.get("note", "").strip()
        checkout_token = data.get("checkout_token", "").strip()
        if not items or not customer_name or not phone or not address:
            raise ValueError("請填寫收件資料並選擇商品")
        if not checkout_token or len(checkout_token) > 100:
            raise ValueError("結帳識別碼無效")

        with db() as con:
            # 序列化「識別碼檢查＋建單」，避免並發重送建立兩筆訂單。
            con.execute("BEGIN IMMEDIATE")
            existing = con.execute(
                "SELECT * FROM orders WHERE checkout_token = ? AND payment_method = 'ecpay_credit'",
                (checkout_token,),
            ).fetchone()
            if existing:
                order = dict(existing)
                order_items = [
                    dict(row)
                    for row in con.execute(
                        "SELECT product_name, quantity FROM order_items WHERE order_id = ? ORDER BY id",
                        (order["id"],),
                    ).fetchall()
                ]
            else:
                admin = con.execute(
                    "SELECT id FROM users WHERE username = ? OR email = ? ORDER BY id ASC LIMIT 1",
                    (DEFAULT_ADMIN_USERNAME, DEFAULT_ADMIN_EMAIL),
                ).fetchone()
                if not admin:
                    raise ValueError("管理員帳號不存在")
                user = self.current_user()
                user_id = (
                    user["id"]
                    if user and user.get("role") == "admin" and user.get("status") == "approved"
                    else admin["id"]
                )
                total = 0
                checked_items = []
                for item in items:
                    product_id = int(item.get("product_id", 0))
                    quantity = int(item.get("quantity", 0))
                    if quantity <= 0:
                        raise ValueError("商品數量需大於 0")
                    product = con.execute(
                        "SELECT * FROM products WHERE id = ? AND status = 'active'",
                        (product_id,),
                    ).fetchone()
                    if not product:
                        raise ValueError("商品不存在或尚未上架")
                    if product["stock"] < quantity:
                        raise ValueError(f"{product['name']} 庫存不足")
                    subtotal = product["price"] * quantity
                    total += subtotal
                    checked_items.append((product, quantity, subtotal))

                merchant_trade_date = datetime.now().strftime("%Y/%m/%d %H:%M:%S")
                for _ in range(5):
                    merchant_trade_no = generate_merchant_trade_no()
                    if not con.execute(
                        "SELECT 1 FROM orders WHERE merchant_trade_no = ?",
                        (merchant_trade_no,),
                    ).fetchone():
                        break
                else:
                    raise RuntimeError("無法產生唯一綠界訂單編號")
                cur = con.execute(
                    """
                    INSERT INTO orders
                    (user_id, customer_name, phone, address, note, total, status, review_status,
                     merchant_trade_no, merchant_trade_date, checkout_token, payment_method,
                     payment_status, payment_amount, inventory_deducted)
                    VALUES (?, ?, ?, ?, ?, ?, 'new', 'pending', ?, ?, ?, 'ecpay_credit',
                            'pending', ?, 0)
                    """,
                    (
                        user_id,
                        customer_name,
                        phone,
                        address,
                        note,
                        total,
                        merchant_trade_no,
                        merchant_trade_date,
                        checkout_token,
                        total,
                    ),
                )
                order_id = cur.lastrowid
                order_items = []
                for product, quantity, subtotal in checked_items:
                    con.execute(
                        """
                        INSERT INTO order_items
                        (order_id, product_id, product_name, quantity, unit_price, subtotal)
                        VALUES (?, ?, ?, ?, ?, ?)
                        """,
                        (order_id, product["id"], product["name"], quantity, product["price"], subtotal),
                    )
                    order_items.append({"product_name": product["name"], "quantity": quantity})
                order = dict(con.execute("SELECT * FROM orders WHERE id = ?", (order_id,)).fetchone())

        parameters = {
            "MerchantID": settings["merchant_id"],
            "MerchantTradeNo": order["merchant_trade_no"],
            "MerchantTradeDate": order["merchant_trade_date"],
            "PaymentType": "aio",
            "TotalAmount": str(order["total"]),
            "TradeDesc": "JASON Hub credit card order",
            "ItemName": build_ecpay_item_name(order_items),
            "ReturnURL": settings["return_url"],
            "OrderResultURL": settings["order_result_url"],
            "ChoosePayment": "Credit",
            "EncryptType": "1",
        }
        parameters["CheckMacValue"] = ecpay_check_mac_value(
            parameters, settings["hash_key"], settings["hash_iv"]
        )
        return self.json(
            {
                "ok": True,
                "order_id": order["id"],
                "payment_url": settings["checkout_url"],
                "parameters": parameters,
            }
        )

    def ecpay_return(self):
        try:
            parameters = self.read_form()
            # 停用新付款時仍須處理已送往綠界的既有訂單 callback。
            settings = ecpay_settings(require_enabled=False)
            if not hmac.compare_digest(
                str(parameters.get("MerchantID", "")), settings["merchant_id"]
            ):
                log_notification_error("ECPay通知 MerchantID 不符")
                return self.text("0|MerchantID Error", 400)
            if not ecpay_verify_check_mac(parameters, settings["hash_key"], settings["hash_iv"]):
                log_notification_error(
                    f"ECPay通知驗證失敗 trade={str(parameters.get('MerchantTradeNo', ''))[:20]}"
                )
                return self.text("0|CheckMacValue Error", 400)
            merchant_trade_no = str(parameters.get("MerchantTradeNo", ""))
            try:
                trade_amount = int(parameters.get("TradeAmt", ""))
                rtn_code = int(parameters.get("RtnCode", ""))
            except (TypeError, ValueError):
                return self.text("0|Invalid Payment Data", 400)
            if rtn_code == 1 and not str(parameters.get("PaymentType", "")).startswith("Credit"):
                return self.text("0|PaymentType Error", 400)
            if (
                rtn_code == 1
                and settings["environment"] == "production"
                and str(parameters.get("SimulatePaid", "0")) == "1"
            ):
                return self.text("0|Simulated Payment Error", 400)

            with db() as con:
                con.execute("BEGIN IMMEDIATE")
                order = con.execute(
                    "SELECT * FROM orders WHERE merchant_trade_no = ? AND payment_method = 'ecpay_credit'",
                    (merchant_trade_no,),
                ).fetchone()
                if not order:
                    log_notification_error(f"ECPay通知找不到訂單 trade={merchant_trade_no[:20]}")
                    return self.text("0|Order Not Found", 404)
                if trade_amount != order["total"] or trade_amount != order["payment_amount"]:
                    log_notification_error(
                        f"ECPay通知金額不符 order={order['id']} received={trade_amount}"
                    )
                    return self.text("0|Amount Error", 400)

                response_json = safe_payment_response(parameters)
                if rtn_code != 1:
                    if order["payment_status"] != "paid":
                        con.execute(
                            """
                            UPDATE orders
                            SET payment_status = 'failed', payment_response = ?, payment_error = ?,
                                payment_callback_processed_at = CURRENT_TIMESTAMP,
                                updated_at = CURRENT_TIMESTAMP
                            WHERE id = ?
                            """,
                            (
                                response_json,
                                str(parameters.get("RtnMsg", "付款失敗"))[:200],
                                order["id"],
                            ),
                        )
                    return self.text("1|OK")

                if order["payment_status"] == "paid" and order["inventory_deducted"] == 1:
                    return self.text("1|OK")

                order_items = con.execute(
                    "SELECT product_id, quantity FROM order_items WHERE order_id = ?",
                    (order["id"],),
                ).fetchall()
                for item in order_items:
                    updated = con.execute(
                        """
                        UPDATE products
                        SET stock = stock - ?, updated_at = CURRENT_TIMESTAMP
                        WHERE id = ? AND stock >= ?
                        """,
                        (item["quantity"], item["product_id"], item["quantity"]),
                    )
                    if updated.rowcount != 1:
                        raise ValueError(f"訂單 {order['id']} 付款成功但庫存不足")
                con.execute(
                    """
                    UPDATE orders
                    SET status = 'paid', payment_status = 'paid', trade_no = ?,
                        ecpay_trade_no = ?, paid_at = ?, payment_response = ?,
                        payment_error = NULL, payment_callback_processed_at = CURRENT_TIMESTAMP,
                        inventory_deducted = 1,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = ? AND inventory_deducted = 0
                    """,
                    (
                        str(parameters.get("TradeNo", ""))[:20] or None,
                        str(parameters.get("TradeNo", ""))[:20] or None,
                        str(parameters.get("PaymentDate", ""))[:30]
                        or datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                        response_json,
                        order["id"],
                    ),
                )
            return self.text("1|OK")
        except Exception as exc:
            log_notification_error(f"ECPay通知處理失敗 {type(exc).__name__}: {str(exc)[:200]}")
            return self.text("0|Error", 500)

    def ecpay_status(self, query):
        merchant_trade_no = "".join(
            ch for ch in str(query.get("trade_no", [""])[0]) if ch.isascii() and ch.isalnum()
        )[:20]
        if not merchant_trade_no:
            return self.error(400, "缺少訂單識別碼")
        with db() as con:
            order = con.execute(
                """
                SELECT id, payment_status, total, paid_at
                FROM orders
                WHERE merchant_trade_no = ? AND payment_method = 'ecpay_credit'
                """,
                (merchant_trade_no,),
            ).fetchone()
        if not order:
            return self.error(404, "找不到付款訂單")
        return self.json({"ok": True, "order": dict(order)})

    def ecpay_result(self, parameters):
        merchant_trade_no = "".join(
            ch for ch in str(parameters.get("MerchantTradeNo", "")) if ch.isascii() and ch.isalnum()
        )[:20]
        order = None
        if merchant_trade_no:
            with db() as con:
                order = con.execute(
                    """
                    SELECT id, payment_status, total
                    FROM orders
                    WHERE merchant_trade_no = ? AND payment_method = 'ecpay_credit'
                    """,
                    (merchant_trade_no,),
                ).fetchone()
        database_status = order["payment_status"] if order else "pending"
        status = database_status
        result_verified = False
        if parameters:
            try:
                settings = ecpay_settings(require_enabled=False)
                result_verified = hmac.compare_digest(
                    str(parameters.get("MerchantID", "")), settings["merchant_id"]
                ) and ecpay_verify_check_mac(
                    parameters, settings["hash_key"], settings["hash_iv"]
                )
            except ValueError:
                result_verified = False
            if not result_verified:
                log_notification_error(
                    f"ECPay消費者結果驗證失敗 trade={merchant_trade_no[:20]}"
                )
        # Client 回傳通過驗證後也只用於顯示，絕不據此標記付款成功。
        if (
            status == "pending"
            and result_verified
            and parameters.get("RtnCode") not in {None, "", "1"}
        ):
            status = "failed"
        labels = {
            "paid": ("付款成功", "後端已收到並驗證綠界付款通知。"),
            "failed": ("付款失敗或已取消", "付款未完成，訂單資料仍已保留。"),
            "cancelled": ("付款已取消", "訂單資料仍已保留。"),
            "refunded": ("款項已退款", "此筆訂單已標記為退款。"),
            "pending": ("付款結果確認中", "正在等待綠界後端付款通知，請稍候。"),
        }
        title, message = labels.get(status, labels["pending"])
        trade_json = json.dumps(merchant_trade_no)
        status_json = json.dumps(database_status)
        order_summary = (
            f"訂單 #{order['id']}｜NT${order['total']:,}"
            if order
            else "尚無可確認的訂單資料"
        )
        content = f"""<!doctype html>
<html lang="zh-Hant"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{html.escape(title)}｜JASON Hub</title><link rel="stylesheet" href="/static/app.css"></head>
<body><main><section class="panel payment-result"><p class="eyebrow">ECPay 信用卡付款</p>
<h1>{html.escape(title)}</h1><p>{html.escape(message)}</p>
<p>{html.escape(order_summary)}</p><a class="button-link primary" href="/">返回商店</a></section></main>
<script>
const tradeNo={trade_json};
const initialStatus={status_json};
if(tradeNo && initialStatus==="pending"){{
 let attempts=0;
 const timer=setInterval(async()=>{{
  if(++attempts>20) return clearInterval(timer);
  try{{
   const response=await fetch("/api/ecpay/status?trade_no="+encodeURIComponent(tradeNo),{{cache:"no-store"}});
   const data=await response.json();
   if(data.ok && data.order.payment_status!=="pending") location.reload();
  }}catch{{}}
 }},3000);
}}
</script></body></html>"""
        return self.text(content, content_type="text/html; charset=utf-8")

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
            order = con.execute(
                "SELECT payment_method FROM orders WHERE id = ?", (order_id,)
            ).fetchone()
            if not order:
                raise ValueError("找不到訂單資料")
            if order["payment_method"] == "ecpay_credit" and status == "paid":
                raise ValueError("綠界訂單只能由通過驗證的付款通知標記為已付款")
            if status is not None:
                con.execute("UPDATE orders SET status = ? WHERE id = ?", (status, order_id))
                if order["payment_method"] == "ecpay_credit" and status == "cancelled":
                    con.execute(
                        """
                        UPDATE orders
                        SET payment_status = 'cancelled', updated_at = CURRENT_TIMESTAMP
                        WHERE id = ? AND payment_status != 'paid'
                        """,
                        (order_id,),
                    )
            if review_status is not None:
                con.execute("UPDATE orders SET review_status = ? WHERE id = ?", (review_status, order_id))
        return self.json({"ok": True})

    def _delete_order_rows(self, con, order_id):
        order = con.execute(
            "SELECT id, review_status, inventory_deducted FROM orders WHERE id = ?",
            (order_id,),
        ).fetchone()
        if not order:
            raise ValueError("找不到訂單資料")
        if order["review_status"] == "pending":
            raise ValueError("只有已審核的訂單可以刪除")
        items = con.execute(
            "SELECT product_id, quantity FROM order_items WHERE order_id = ?",
            (order_id,),
        ).fetchall()
        if order["inventory_deducted"]:
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



