import json
import os
import tempfile
import threading
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import server


class EcpayIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp_dir = tempfile.TemporaryDirectory()
        cls.original_db_path = server.DB_PATH
        cls.original_products_path = server.PRODUCTS_JSON_PATH
        server.DB_PATH = os.path.join(cls.temp_dir.name, "test.db")
        server.PRODUCTS_JSON_PATH = os.path.join(cls.temp_dir.name, "missing-products.json")
        cls.environment = {
            "ECPAY_MERCHANT_ID": "UNITTEST1",
            "ECPAY_HASH_KEY": "unit-test-hash-key",
            "ECPAY_HASH_IV": "unit-test-hash-iv",
            "ECPAY_ENABLED": "true",
            "ECPAY_ENV": "stage",
            "ECPAY_RETURN_URL": "https://shop.example/ecpay/return",
            "ECPAY_ORDER_RESULT_URL": "https://shop.example/ecpay/result",
        }
        cls.original_environment = {key: os.environ.get(key) for key in cls.environment}
        os.environ.update(cls.environment)
        server.init_db()
        with server.db() as con:
            con.execute(
                """
                INSERT INTO products
                (name, category, description, price, stock, status, featured, preview_url, image_url)
                VALUES ('測試商品', '測試', '', 120, 10, 'active', 0, '', '')
                """
            )
            cls.product_id = con.execute(
                "SELECT id FROM products WHERE name = '測試商品'"
            ).fetchone()["id"]
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
        server.PRODUCTS_JSON_PATH = cls.original_products_path
        for key, value in cls.original_environment.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        cls.temp_dir.cleanup()

    def request(self, path, method="GET", body=None, content_type="application/json"):
        data = None
        if body is not None:
            data = body if isinstance(body, bytes) else body.encode("utf-8")
        request = Request(
            self.base_url + path,
            data=data,
            method=method,
            headers={"Content-Type": content_type},
        )
        try:
            with urlopen(request, timeout=5) as response:
                return response.status, response.read().decode("utf-8")
        except HTTPError as error:
            return error.code, error.read().decode("utf-8")

    def create_checkout(self, token):
        payload = {
            "items": [{"product_id": self.product_id, "quantity": 2}],
            "customer_name": "測試顧客",
            "phone": "0900000000",
            "address": "測試地址",
            "note": "",
            "checkout_token": token,
            "total": 1,
        }
        status, body = self.request(
            "/api/ecpay/checkout", "POST", json.dumps(payload, ensure_ascii=False)
        )
        self.assertEqual(status, 200, body)
        return json.loads(body)

    def signed_result(self, checkout, rtn_code="1"):
        parameters = {
            "MerchantID": self.environment["ECPAY_MERCHANT_ID"],
            "MerchantTradeNo": checkout["parameters"]["MerchantTradeNo"],
            "RtnCode": rtn_code,
        }
        parameters["CheckMacValue"] = server.ecpay_check_mac_value(
            parameters,
            self.environment["ECPAY_HASH_KEY"],
            self.environment["ECPAY_HASH_IV"],
        )
        return parameters

    def callback(self, checkout, **overrides):
        parameters = {
            "MerchantID": self.environment["ECPAY_MERCHANT_ID"],
            "MerchantTradeNo": checkout["parameters"]["MerchantTradeNo"],
            "RtnCode": "1",
            "RtnMsg": "Succeeded",
            "TradeNo": "240101000000001",
            "TradeAmt": checkout["parameters"]["TotalAmount"],
            "PaymentDate": "2026/07/25 12:00:00",
            "PaymentType": "Credit_CreditCard",
            "SimulatePaid": "0",
        }
        parameters.update(overrides)
        parameters["CheckMacValue"] = server.ecpay_check_mac_value(
            parameters,
            self.environment["ECPAY_HASH_KEY"],
            self.environment["ECPAY_HASH_IV"],
        )
        return self.request(
            "/ecpay/return",
            "POST",
            urlencode(parameters),
            "application/x-www-form-urlencoded",
        )

    def test_01_known_check_mac_example(self):
        parameters = {
            "MerchantID": "UNITTEST1",
            "MerchantTradeNo": "ORDER123456",
            "MerchantTradeDate": "2026/07/25 12:00:00",
            "PaymentType": "aio",
            "TotalAmount": "240",
            "TradeDesc": "Unit test order",
            "ItemName": "Test item x 2",
            "ReturnURL": "https://shop.example/ecpay/return",
            "ChoosePayment": "Credit",
            "EncryptType": "1",
        }
        self.assertEqual(
            server.ecpay_check_mac_value(
                parameters, "unit-test-hash-key", "unit-test-hash-iv"
            ),
            "343DFA93D6F4E4EB23464B1A11445F318CFD1548BC6CFF5C97D1C8F2290C44A2",
        )
        tampered = {**parameters, "TotalAmount": "241"}
        self.assertFalse(
            server.ecpay_verify_check_mac(
                {**tampered, "CheckMacValue": "343DFA93D6F4E4EB23464B1A11445F318CFD1548BC6CFF5C97D1C8F2290C44A2"},
                "unit-test-hash-key",
                "unit-test-hash-iv",
            )
        )

    def test_01b_environment_and_api_selection(self):
        settings = server.ecpay_settings()
        self.assertEqual(settings["environment"], "stage")
        self.assertEqual(settings["checkout_url"], server.ECPAY_STAGE_URL)
        production = {**self.environment, "ECPAY_ENV": "production", "ECPAY_MERCHANT_ID": "LIVEUNIT01"}
        with patch.dict(os.environ, production, clear=False):
            self.assertEqual(server.ecpay_settings()["checkout_url"], server.ECPAY_PRODUCTION_URL)
        production["ECPAY_MERCHANT_ID"] = next(iter(server.ECPAY_TEST_MERCHANT_IDS))
        with patch.dict(os.environ, production, clear=False):
            with self.assertRaisesRegex(ValueError, "測試特店編號"):
                server.ecpay_settings()

    def test_01c_missing_environment_values_and_disabled_switch(self):
        for key in ("ECPAY_MERCHANT_ID", "ECPAY_HASH_KEY", "ECPAY_HASH_IV"):
            with self.subTest(key=key), patch.dict(os.environ, self.environment, clear=False):
                os.environ.pop(key, None)
                with self.assertRaisesRegex(ValueError, key):
                    server.ecpay_settings()
        with patch.dict(os.environ, {**self.environment, "ECPAY_ENABLED": "false"}, clear=False):
            with self.assertRaisesRegex(ValueError, "目前已停用"):
                server.ecpay_settings()
            self.assertFalse(server.ecpay_settings(require_enabled=False)["enabled"])

    def test_01d_https_callback_urls_required(self):
        with patch.dict(
            os.environ,
            {**self.environment, "ECPAY_RETURN_URL": "http://shop.example/ecpay/return"},
            clear=False,
        ):
            with self.assertRaisesRegex(ValueError, "HTTPS"):
                server.ecpay_settings()

    def test_02_checkout_recalculates_total_and_is_idempotent(self):
        first = self.create_checkout("checkout-idempotent")
        second = self.create_checkout("checkout-idempotent")
        self.assertEqual(first["order_id"], second["order_id"])
        self.assertEqual(first["parameters"]["TotalAmount"], "240")
        self.assertEqual(first["parameters"]["ChoosePayment"], "Credit")
        self.assertEqual(
            first["payment_url"], "https://payment-stage.ecpay.com.tw/Cashier/AioCheckOut/V5"
        )
        with server.db() as con:
            count = con.execute(
                "SELECT COUNT(*) AS c FROM orders WHERE checkout_token = 'checkout-idempotent'"
            ).fetchone()["c"]
            buyer = con.execute(
                """
                SELECT customer_name, phone, address, note
                FROM orders WHERE checkout_token = 'checkout-idempotent'
                """
            ).fetchone()
            stock = con.execute(
                "SELECT stock FROM products WHERE id = ?", (self.product_id,)
            ).fetchone()["stock"]
        self.assertEqual(count, 1)
        self.assertEqual(
            tuple(buyer),
            ("測試顧客", "0900000000", "測試地址", ""),
        )
        self.assertEqual(stock, 10)

    def test_02b_empty_missing_product_and_insufficient_stock(self):
        base = {
            "customer_name": "測試顧客",
            "phone": "0900000000",
            "address": "測試地址",
            "checkout_token": "invalid-cart",
        }
        status, _ = self.request(
            "/api/ecpay/checkout", "POST", json.dumps({**base, "items": []}, ensure_ascii=False)
        )
        self.assertEqual(status, 400)
        status, _ = self.request(
            "/api/ecpay/checkout",
            "POST",
            json.dumps(
                {**base, "checkout_token": "missing-product", "items": [{"product_id": 999999, "quantity": 1}]},
                ensure_ascii=False,
            ),
        )
        self.assertEqual(status, 400)
        status, _ = self.request(
            "/api/ecpay/checkout",
            "POST",
            json.dumps(
                {
                    **base,
                    "checkout_token": "insufficient-stock",
                    "items": [{"product_id": self.product_id, "quantity": 999}],
                },
                ensure_ascii=False,
            ),
        )
        self.assertEqual(status, 400)

    def test_02c_merchant_trade_number_is_unique_and_within_limit(self):
        first = self.create_checkout("unique-one")
        second = self.create_checkout("unique-two")
        first_number = first["parameters"]["MerchantTradeNo"]
        second_number = second["parameters"]["MerchantTradeNo"]
        self.assertNotEqual(first_number, second_number)
        self.assertLessEqual(len(first_number), 20)
        self.assertTrue(first_number.isalnum())

    def test_03_invalid_mac_amount_and_unknown_order_are_rejected(self):
        checkout = self.create_checkout("checkout-invalid")
        parameters = {
            "MerchantTradeNo": checkout["parameters"]["MerchantTradeNo"],
            "TradeAmt": "240",
            "RtnCode": "1",
            "CheckMacValue": "BAD",
        }
        status, _ = self.request(
            "/ecpay/return",
            "POST",
            urlencode(parameters),
            "application/x-www-form-urlencoded",
        )
        self.assertEqual(status, 400)
        status, _ = self.callback(checkout, TradeAmt="999")
        self.assertEqual(status, 400)
        status, _ = self.callback(checkout, MerchantTradeNo="DOESNOTEXIST")
        self.assertEqual(status, 404)
        with server.db() as con:
            order = con.execute(
                "SELECT payment_status, inventory_deducted FROM orders WHERE id = ?",
                (checkout["order_id"],),
            ).fetchone()
        self.assertEqual(tuple(order), ("pending", 0))

    def test_03b_callback_merchant_id_mismatch_is_rejected(self):
        checkout = self.create_checkout("merchant-mismatch")
        status, _ = self.callback(checkout, MerchantID="OTHERSTORE")
        self.assertEqual(status, 400)
        with server.db() as con:
            order = con.execute(
                "SELECT payment_status FROM orders WHERE id = ?", (checkout["order_id"],)
            ).fetchone()
        self.assertEqual(order["payment_status"], "pending")

    def test_04_success_callback_is_idempotent(self):
        checkout = self.create_checkout("checkout-success")
        with patch.object(server, "send_discord_member_apply_notification") as discord_mock, patch.object(
            server, "send_gmail_member_apply_notification"
        ) as mail_mock:
            first_status, first_body = self.callback(checkout)
            second_status, second_body = self.callback(checkout)
            discord_mock.assert_not_called()
            mail_mock.assert_not_called()
        self.assertEqual((first_status, first_body), (200, "1|OK"))
        self.assertEqual((second_status, second_body), (200, "1|OK"))
        with server.db() as con:
            order = con.execute(
                "SELECT payment_status, inventory_deducted FROM orders WHERE id = ?",
                (checkout["order_id"],),
            ).fetchone()
            stock = con.execute(
                "SELECT stock FROM products WHERE id = ?", (self.product_id,)
            ).fetchone()["stock"]
        self.assertEqual(tuple(order), ("paid", 1))
        self.assertEqual(stock, 8)
        with server.db() as con:
            callback_fields = con.execute(
                """
                SELECT ecpay_trade_no, payment_callback_processed_at, payment_error
                FROM orders WHERE id = ?
                """,
                (checkout["order_id"],),
            ).fetchone()
        self.assertTrue(callback_fields["ecpay_trade_no"])
        self.assertTrue(callback_fields["payment_callback_processed_at"])
        self.assertIsNone(callback_fields["payment_error"])

    def test_05_failure_and_result_page_never_mark_paid(self):
        checkout = self.create_checkout("checkout-failed")
        status, body = self.callback(checkout, RtnCode="10100058", RtnMsg="Failed")
        self.assertEqual((status, body), (200, "1|OK"))
        result_status, result_body = self.request(
            "/ecpay/result",
            "POST",
            urlencode(self.signed_result(checkout)),
            "application/x-www-form-urlencoded",
        )
        self.assertEqual(result_status, 200)
        self.assertIn("付款失敗", result_body)
        with server.db() as con:
            order = con.execute(
                """
                SELECT payment_status, inventory_deducted, payment_error,
                       payment_callback_processed_at
                FROM orders WHERE id = ?
                """,
                (checkout["order_id"],),
            ).fetchone()
        self.assertEqual(order["payment_status"], "failed")
        self.assertEqual(order["inventory_deducted"], 0)
        self.assertTrue(order["payment_error"])
        self.assertTrue(order["payment_callback_processed_at"])

    def test_06_direct_result_page_is_unconfirmed(self):
        status, body = self.request("/ecpay/result")
        self.assertEqual(status, 200)
        self.assertIn("付款結果確認中", body)

    def test_07_cancelled_browser_result_only_changes_display(self):
        checkout = self.create_checkout("checkout-cancelled")
        status, body = self.request(
            "/ecpay/result",
            "POST",
            urlencode(self.signed_result(checkout, "10100058")),
            "application/x-www-form-urlencoded",
        )
        self.assertEqual(status, 200)
        self.assertIn("付款失敗或已取消", body)
        with server.db() as con:
            order = con.execute(
                "SELECT payment_status FROM orders WHERE id = ?", (checkout["order_id"],)
            ).fetchone()
        self.assertEqual(order["payment_status"], "pending")

    def test_08_order_result_before_return_stays_pending_then_becomes_paid(self):
        checkout = self.create_checkout("result-before-return")
        status, body = self.request(
            "/ecpay/result",
            "POST",
            urlencode(self.signed_result(checkout)),
            "application/x-www-form-urlencoded",
        )
        self.assertEqual(status, 200)
        self.assertIn("付款結果確認中", body)
        self.assertEqual(self.callback(checkout), (200, "1|OK"))
        status, body = self.request(
            "/ecpay/result",
            "POST",
            urlencode(self.signed_result(checkout)),
            "application/x-www-form-urlencoded",
        )
        self.assertEqual(status, 200)
        self.assertIn("付款成功", body)

    def test_09_invalid_result_mac_never_marks_paid(self):
        checkout = self.create_checkout("invalid-result-mac")
        status, body = self.request(
            "/ecpay/result",
            "POST",
            urlencode(
                {
                    "MerchantID": self.environment["ECPAY_MERCHANT_ID"],
                    "MerchantTradeNo": checkout["parameters"]["MerchantTradeNo"],
                    "RtnCode": "1",
                    "CheckMacValue": "BAD",
                }
            ),
            "application/x-www-form-urlencoded",
        )
        self.assertEqual(status, 200)
        self.assertIn("付款結果確認中", body)
        with server.db() as con:
            status_value = con.execute(
                "SELECT payment_status FROM orders WHERE id = ?", (checkout["order_id"],)
            ).fetchone()["payment_status"]
        self.assertEqual(status_value, "pending")

    def test_10_original_member_order_cart_and_notification_regression(self):
        status, body = self.request("/api/me")
        self.assertEqual(status, 200)
        self.assertIsNone(json.loads(body)["user"])
        status, body = self.request(
            "/api/login",
            "POST",
            json.dumps(
                {
                    "username": server.DEFAULT_ADMIN_USERNAME,
                    "password": server.DEFAULT_ADMIN_PASSWORD,
                }
            ),
        )
        self.assertEqual(status, 200, body)
        status, body = self.request("/api/products")
        self.assertEqual(status, 200)
        self.assertTrue(json.loads(body)["products"])
        manual_payload = {
            "items": [{"product_id": self.product_id, "quantity": 1}],
            "customer_name": "原流程測試",
            "phone": "0900000000",
            "address": "測試地址",
            "note": "",
        }
        status, body = self.request(
            "/api/orders", "POST", json.dumps(manual_payload, ensure_ascii=False)
        )
        self.assertEqual(status, 200, body)
        with patch.object(server, "send_discord_member_apply_notification") as discord_mock, patch.object(
            server, "send_gmail_member_apply_notification"
        ) as mail_mock:
            server.notify_member_apply(
                name="測試", email="test@example.com", phone="0900000000",
                account="test", created_at="2026-07-25 12:00:00"
            )
            discord_mock.assert_called_once()
            mail_mock.assert_called_once()
        with open(os.path.join(server.STATIC_DIR, "app.js"), encoding="utf-8-sig") as frontend:
            script = frontend.read()
        self.assertIn('localStorage.getItem("studio_cart")', script)
        self.assertIn("/api/orders", script)
        self.assertIn("/api/ecpay/checkout", script)


if __name__ == "__main__":
    unittest.main()
