import json
import os
import tempfile
import threading
import unittest
from types import SimpleNamespace
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import chatbot_service
import server


class ChatbotTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp_dir = tempfile.TemporaryDirectory()
        cls.original_db_path = server.DB_PATH
        cls.original_products_path = server.PRODUCTS_JSON_PATH
        server.DB_PATH = os.path.join(cls.temp_dir.name, "chatbot.db")
        server.PRODUCTS_JSON_PATH = os.path.join(cls.temp_dir.name, "missing-products.json")
        server.init_db()
        con = server.db()
        try:
            con.execute(
                """
                INSERT INTO products
                (name, category, description, price, stock, status, featured, preview_url, image_url)
                VALUES ('客服測試商品', '測試分類', '商品實際介紹', 123, 5, 'active', 1, '', '')
                """
            )
            con.commit()
        finally:
            con.close()
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
        cls.temp_dir.cleanup()

    def setUp(self):
        self.environment = patch.dict(
            os.environ,
            {
                "OPENAI_API_KEY": "test-key",
                "OPENAI_MODEL": "test-model",
                "AI_CHAT_ENABLED": "true",
                "AI_MAX_MESSAGE_LENGTH": "500",
                "AI_MAX_OUTPUT_TOKENS": "300",
                "AI_RATE_LIMIT_PER_MINUTE": "5",
                "AI_RATE_LIMIT_PER_HOUR": "20",
                "AI_HISTORY_MAX_ROUNDS": "4",
            },
        )
        self.environment.start()
        chatbot_service.reset_rate_limits()

    def tearDown(self):
        self.environment.stop()

    def post_chat(self, payload):
        request = Request(
            self.base_url + "/api/chat",
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            method="POST",
            headers={"Content-Type": "application/json"},
        )
        try:
            with urlopen(request, timeout=5) as response:
                return response.status, json.loads(response.read().decode("utf-8"))
        except HTTPError as error:
            try:
                return error.code, json.loads(error.read().decode("utf-8"))
            finally:
                error.close()

    def get_json(self, path):
        with urlopen(self.base_url + path, timeout=5) as response:
            return response.status, json.loads(response.read().decode("utf-8"))

    def test_chat_uses_existing_active_product_data(self):
        with patch.object(chatbot_service, "ask_ai", return_value="這是測試回覆") as ask_ai:
            status, payload = self.post_chat(
                {
                    "message": "有什麼商品？",
                    "history": [{"role": "user", "content": "前一題"}],
                }
            )

        self.assertEqual(status, 200)
        self.assertEqual(payload, {"ok": True, "reply": "這是測試回覆"})
        products = ask_ai.call_args.args[1]
        product = next(item for item in products if item["name"] == "客服測試商品")
        self.assertEqual(product["price"], 123)
        self.assertEqual(ask_ai.call_args.args[2], [{"role": "user", "content": "前一題"}])

    def test_empty_and_oversized_messages_are_rejected(self):
        for message, expected_error in (
            ("   ", "請輸入問題"),
            ("字" * 501, "您的問題內容過長，請縮短後再試。"),
        ):
            with self.subTest(expected_error=expected_error):
                status, payload = self.post_chat({"message": message})
                self.assertEqual(status, 400)
                self.assertFalse(payload["ok"])
                self.assertEqual(payload["error"], expected_error)

    def test_missing_key_returns_safe_error_without_leaking_secret(self):
        with patch.dict(os.environ, {"OPENAI_API_KEY": ""}):
            status, payload = self.post_chat({"message": "付款方式？"})

        self.assertEqual(status, 503)
        self.assertEqual(payload["error"], "AI 客服目前暫時無法使用。")
        self.assertNotIn("OPENAI_API_KEY", json.dumps(payload, ensure_ascii=False))

    def test_disabled_switch_prevents_provider_call(self):
        with patch.dict(os.environ, {"AI_CHAT_ENABLED": "false"}), patch.object(
            chatbot_service, "ask_ai"
        ) as ask_ai:
            status, payload = self.post_chat({"message": "有哪些商品？"})
        self.assertEqual(status, 503)
        self.assertEqual(payload["error"], "AI 客服目前暫停服務。")
        ask_ai.assert_not_called()
        with patch.dict(os.environ, {"AI_CHAT_ENABLED": "false"}):
            status, payload = self.get_json("/api/chat/status")
        self.assertEqual(status, 200)
        self.assertFalse(payload["enabled"])
        self.assertEqual(payload["max_message_length"], 500)

    def test_provider_failure_does_not_break_site(self):
        with patch.object(
            chatbot_service,
            "ask_ai",
            side_effect=chatbot_service.ChatbotUnavailableError("private provider detail"),
        ):
            status, payload = self.post_chat({"message": "文章有哪些？"})
        self.assertEqual(status, 503)
        self.assertNotIn("private provider detail", json.dumps(payload, ensure_ascii=False))

        with urlopen(self.base_url + "/", timeout=5) as response:
            page = response.read().decode("utf-8")
        self.assertEqual(response.status, 200)
        self.assertIn('id="chatbot"', page)
        self.assertIn('/static/chatbot.js', page)
        self.assertIn('/static/chatbot.css', page)

    def test_openai_responses_api_configuration(self):
        products = [{"name": "商品", "category": "分類", "price": 100, "description": "介紹"}]
        response = SimpleNamespace(
            output_text="安全回覆",
            usage=SimpleNamespace(input_tokens=120, output_tokens=30, total_tokens=150),
        )
        history = [{"role": "user", "content": "前一題"}, {"role": "assistant", "content": "前一答"}]
        with patch("openai.OpenAI") as openai_client, patch("builtins.print") as print_log:
            openai_client.return_value.responses.create.return_value = response
            reply = chatbot_service.ask_ai("如何購買？", products, history)

        self.assertEqual(reply, "安全回覆")
        openai_client.assert_called_once_with(api_key="test-key", timeout=20)
        request = openai_client.return_value.responses.create.call_args.kwargs
        self.assertEqual(request["model"], "test-model")
        self.assertEqual(request["input"][-1], {"role": "user", "content": "如何購買？"})
        self.assertEqual(len(request["input"]), 3)
        self.assertIn("NT$100", request["instructions"])
        self.assertEqual(request["max_output_tokens"], 300)
        self.assertFalse(request["store"])
        print_log.assert_called_once_with(
            "[ai-chat-usage] model=test-model input_tokens=120 output_tokens=30 total_tokens=150"
        )

    def test_minute_and_hour_rate_limits(self):
        for index in range(5):
            self.assertTrue(chatbot_service.check_rate_limit("test-client", now=float(index)))
        self.assertFalse(chatbot_service.check_rate_limit("test-client", now=5.0))

        chatbot_service.reset_rate_limits()
        for index in range(20):
            self.assertTrue(chatbot_service.check_rate_limit("hour-client", now=float(index * 61)))
        self.assertFalse(chatbot_service.check_rate_limit("hour-client", now=1220.0))

    def test_history_is_limited_and_sanitized(self):
        history = [
            {"role": "user" if index % 2 == 0 else "assistant", "content": f"訊息 {index}"}
            for index in range(12)
        ]
        history.extend(({"role": "system", "content": "不允許"}, {"role": "user", "content": 123}))
        sanitized = chatbot_service.sanitize_history(history)
        self.assertLessEqual(len(sanitized), 8)
        self.assertNotIn("system", {item["role"] for item in sanitized})


if __name__ == "__main__":
    unittest.main()
