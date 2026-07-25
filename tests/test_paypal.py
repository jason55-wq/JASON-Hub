import json
import os
import tempfile
import threading
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import server


class PayPalIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp_dir = tempfile.TemporaryDirectory()
        cls.original_db_path = server.DB_PATH
        server.DB_PATH = os.path.join(cls.temp_dir.name, "paypal.db")
        cls.environment = patch.dict(
            os.environ,
            {
                "RENDER": "false",
                "APP_ENV": "development",
                "PAYPAL_CLIENT_ID": "sandbox-client-id",
                "PAYPAL_CLIENT_SECRET": "sandbox-secret",
                "PAYPAL_MODE": "sandbox",
                "PAYPAL_CURRENCY": "USD",
                "PAYPAL_WEBHOOK_ID": "sandbox-webhook-id",
                "PAYPAL_TWD_PER_USD": "30",
                "BASE_URL": "http://127.0.0.1",
            },
            clear=False,
        )
        cls.environment.start()
        os.environ.pop("DATABASE_URL", None)
        server.init_db()
        with server.db() as con:
            cls.owner_id = server.insert_and_get_id(
                con,
                """
                INSERT INTO users (username, email, password_hash, role, status)
                VALUES ('paypal-owner', 'owner@example.com', ?, 'member', 'approved')
                """,
                (server.hash_password("owner-password"),),
            )
            cls.other_id = server.insert_and_get_id(
                con,
                """
                INSERT INTO users (username, email, password_hash, role, status)
                VALUES ('paypal-other', 'other@example.com', ?, 'member', 'approved')
                """,
                (server.hash_password("other-password"),),
            )
            cls.product_id = server.insert_and_get_id(
                con,
                """
                INSERT INTO products
                (name, category, description, price, stock, status, featured, preview_url, image_url)
                VALUES ('PayPal Product', 'Test', '', 300, 200, 'active', 0, '', '')
                """
            )
            cls.owner_token = "owner-session-token"
            cls.other_token = "other-session-token"
            con.execute(
                "INSERT INTO sessions (token, user_id, expires_at) VALUES (?, ?, ?)",
                (cls.owner_token, cls.owner_id, 4102444800),
            )
            con.execute(
                "INSERT INTO sessions (token, user_id, expires_at) VALUES (?, ?, ?)",
                (cls.other_token, cls.other_id, 4102444800),
            )
        cls.httpd = server.ThreadingHTTPServer(("127.0.0.1", 0), server.App)
        cls.thread = threading.Thread(target=cls.httpd.serve_forever, daemon=True)
        cls.thread.start()
        cls.base_url = f"http://127.0.0.1:{cls.httpd.server_port}"

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        cls.httpd.server_close()
        cls.thread.join(timeout=5)
        server.DB_PATH = cls.original_db_path
        cls.environment.stop()
        cls.temp_dir.cleanup()

    def request(self, path, method="GET", payload=None, token=None, headers=None):
        body = None if payload is None else json.dumps(payload).encode()
        token = token or self.owner_token
        request_headers = {
            "Content-Type": "application/json",
            "Cookie": f"studio_session={token}",
            **(headers or {}),
        }
        if method != "GET" and path != "/api/paypal/webhook":
            request_headers["X-CSRF-Token"] = server.hashlib.sha256(
                f"jason-hub-csrf:{token}".encode()
            ).hexdigest()
        request = Request(
            self.base_url + path,
            data=body,
            method=method,
            headers=request_headers,
        )
        try:
            with urlopen(request, timeout=5) as response:
                return response.status, json.loads(response.read().decode())
        except HTTPError as error:
            return error.code, json.loads(error.read().decode())

    def create_response(self, paypal_id):
        return {"id": paypal_id, "status": "CREATED", "purchase_units": []}

    def capture_response(self, paypal_id, **overrides):
        with server.db() as con:
            order = con.execute(
                "SELECT * FROM orders WHERE paypal_order_id = ?", (paypal_id,)
            ).fetchone()
        capture = {
            "id": f"CAP-{order['id']}",
            "status": "COMPLETED",
            "amount": {
                "value": order["paypal_amount"],
                "currency_code": order["paypal_currency"],
            },
            "custom_id": str(order["id"]),
            "invoice_id": order["paypal_invoice_id"],
        }
        capture.update(overrides.pop("capture", {}))
        result = {
            "id": paypal_id,
            "status": "COMPLETED",
            "purchase_units": [
                {
                    "custom_id": str(order["id"]),
                    "invoice_id": order["paypal_invoice_id"],
                    "payments": {"captures": [capture]},
                }
            ],
        }
        result.update(overrides)
        return result

    def checkout_payload(self, token):
        return {
            "items": [{"product_id": self.product_id, "quantity": 2}],
            "customer_name": "PayPal Buyer",
            "phone": "0900000000",
            "address": "Taipei",
            "note": "",
            "checkout_token": token,
            "total": "0.01",
        }

    def create_order(self, token):
        paypal_id = f"PAYPAL-{token.upper()}"
        with patch.object(
            server, "paypal_api_request", return_value=self.create_response(paypal_id)
        ):
            status, data = self.request(
                "/api/paypal/orders", "POST", self.checkout_payload(token)
            )
        self.assertEqual(status, 200, data)
        return data

    def capture(self, checkout, response=None, token=None):
        response = response or self.capture_response(checkout["order_id"])
        with patch.object(server, "paypal_api_request", return_value=response):
            return self.request(
                "/api/paypal/orders/capture",
                "POST",
                {"order_id": checkout["order_id"]},
                token=token,
            )

    def test_01_create_recalculates_amount_and_ignores_forged_total(self):
        checkout = self.create_order("create-recalculate")
        with server.db() as con:
            order = con.execute(
                "SELECT total, paypal_amount, paypal_currency, inventory_deducted FROM orders WHERE id = ?",
                (checkout["internal_order_id"],),
            ).fetchone()
            stock = con.execute(
                "SELECT stock FROM products WHERE id = ?", (self.product_id,)
            ).fetchone()["stock"]
        self.assertEqual(tuple(order), (600, "20.00", "USD", 0))
        self.assertEqual(stock, 200)

    def test_02_capture_success_and_duplicate_capture_are_idempotent(self):
        checkout = self.create_order("capture-success")
        before = self._stock()
        first_status, first = self.capture(checkout)
        second_status, second = self.capture(checkout)
        self.assertEqual((first_status, first["status"]), (200, "COMPLETED"))
        self.assertEqual((second_status, second["already_processed"]), (200, True))
        self.assertEqual(self._stock(), before - 2)

    def test_03_capture_failure_never_pays_or_deducts_stock(self):
        checkout = self.create_order("capture-failure")
        response = self.capture_response(
            checkout["order_id"],
            status="APPROVED",
            capture={"status": "DECLINED"},
        )
        before = self._stock()
        status, _ = self.capture(checkout, response)
        self.assertEqual(status, 400)
        self.assert_order_state(checkout, "failed", 0)
        self.assertEqual(self._stock(), before)

    def test_04_amount_mismatch_is_rejected(self):
        checkout = self.create_order("amount-mismatch")
        response = self.capture_response(
            checkout["order_id"], capture={"amount": {"value": "0.01", "currency_code": "USD"}}
        )
        status, _ = self.capture(checkout, response)
        self.assertEqual(status, 400)
        self.assert_order_state(checkout, "failed", 0)

    def test_05_currency_mismatch_is_rejected(self):
        checkout = self.create_order("currency-mismatch")
        response = self.capture_response(
            checkout["order_id"], capture={"amount": {"value": "20.00", "currency_code": "EUR"}}
        )
        status, _ = self.capture(checkout, response)
        self.assertEqual(status, 400)
        self.assert_order_state(checkout, "failed", 0)

    def test_06_non_owner_cannot_capture(self):
        checkout = self.create_order("wrong-owner")
        status, _ = self.capture(checkout, token=self.other_token)
        self.assertEqual(status, 403)
        self.assert_order_state(checkout, "pending", 0)

    def test_07_already_paid_order_cannot_create_another_payment(self):
        checkout = self.create_order("already-paid")
        self.capture(checkout)
        with patch.object(server, "paypal_api_request") as api_mock:
            status, _ = self.request(
                "/api/paypal/orders", "POST", self.checkout_payload("already-paid")
            )
        self.assertEqual(status, 409)
        api_mock.assert_not_called()

    def test_08_api_timeout_is_safe(self):
        with patch.object(
            server, "paypal_api_request", side_effect=RuntimeError("timeout")
        ):
            status, _ = self.request(
                "/api/paypal/orders", "POST", self.checkout_payload("api-timeout")
            )
        self.assertEqual(status, 503)
        with server.db() as con:
            order = con.execute(
                "SELECT payment_status, inventory_deducted FROM orders WHERE checkout_token = 'api-timeout'"
            ).fetchone()
        self.assertEqual(tuple(order), ("pending", 0))

    def test_09_missing_csrf_is_rejected(self):
        request = Request(
            self.base_url + "/api/paypal/orders",
            data=json.dumps(self.checkout_payload("missing-csrf")).encode(),
            method="POST",
            headers={
                "Content-Type": "application/json",
                "Cookie": f"studio_session={self.owner_token}",
            },
        )
        with self.assertRaises(HTTPError) as raised:
            urlopen(request, timeout=5)
        self.assertEqual(raised.exception.code, 403)

    def test_10_verified_webhook_is_idempotent(self):
        checkout = self.create_order("webhook-repeat")
        capture = self.capture_response(checkout["order_id"])
        resource = capture["purchase_units"][0]["payments"]["captures"][0]
        resource["supplementary_data"] = {
            "related_ids": {"order_id": checkout["order_id"]}
        }
        event = {
            "id": "WH-REPEAT",
            "event_type": "PAYMENT.CAPTURE.COMPLETED",
            "resource": resource,
        }
        headers = {
            "Paypal-Transmission-Id": "transmission",
            "Paypal-Transmission-Time": "2026-07-25T00:00:00Z",
            "Paypal-Cert-Url": "https://api.paypal.com/cert",
            "Paypal-Auth-Algo": "SHA256withRSA",
            "Paypal-Transmission-Sig": "signature",
        }
        before = self._stock()
        with patch.object(
            server,
            "paypal_api_request",
            return_value={"verification_status": "SUCCESS"},
        ):
            first = self.request(
                "/api/paypal/webhook", "POST", event, headers=headers
            )
            second = self.request(
                "/api/paypal/webhook", "POST", event, headers=headers
            )
        self.assertEqual(first[0], 200)
        self.assertEqual((second[0], second[1]["duplicate"]), (200, True))
        self.assertEqual(self._stock(), before - 2)
        with server.db() as con:
            count = con.execute(
                "SELECT COUNT(*) AS c FROM paypal_webhook_events WHERE event_id = 'WH-REPEAT'"
            ).fetchone()["c"]
        self.assertEqual(count, 1)

    def test_11_unverified_webhook_never_updates_order(self):
        checkout = self.create_order("webhook-invalid")
        event = {
            "id": "WH-INVALID",
            "event_type": "PAYMENT.CAPTURE.COMPLETED",
            "resource": {"id": "CAP-INVALID"},
        }
        headers = {
            "Paypal-Transmission-Id": "transmission",
            "Paypal-Transmission-Time": "2026-07-25T00:00:00Z",
            "Paypal-Cert-Url": "https://api.paypal.com/cert",
            "Paypal-Auth-Algo": "SHA256withRSA",
            "Paypal-Transmission-Sig": "bad",
        }
        with patch.object(
            server,
            "paypal_api_request",
            return_value={"verification_status": "FAILURE"},
        ):
            status, _ = self.request(
                "/api/paypal/webhook", "POST", event, headers=headers
            )
        self.assertEqual(status, 400)
        self.assert_order_state(checkout, "pending", 0)

    def _stock(self):
        with server.db() as con:
            return con.execute(
                "SELECT stock FROM products WHERE id = ?", (self.product_id,)
            ).fetchone()["stock"]

    def assert_order_state(self, checkout, payment_status, inventory_deducted):
        with server.db() as con:
            order = con.execute(
                "SELECT payment_status, inventory_deducted FROM orders WHERE id = ?",
                (checkout["internal_order_id"],),
            ).fetchone()
        self.assertEqual(tuple(order), (payment_status, inventory_deducted))


if __name__ == "__main__":
    unittest.main()
