import http.client
import threading
import unittest

import server


class ArticleRouteTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.httpd = server.ThreadingHTTPServer(("127.0.0.1", 0), server.App)
        cls.thread = threading.Thread(target=cls.httpd.serve_forever, daemon=True)
        cls.thread.start()
        cls.host, cls.port = cls.httpd.server_address

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        cls.httpd.server_close()
        cls.thread.join(timeout=2)

    def get(self, path):
        connection = http.client.HTTPConnection(self.host, self.port, timeout=5)
        connection.request("GET", path)
        response = connection.getresponse()
        body = response.read().decode("utf-8")
        connection.close()
        return response.status, response.getheader("Content-Type"), body

    def test_article_archive_routes_serve_existing_application(self):
        paths = (
            "/articles",
            "/articles/2026",
            "/articles/2026/08",
            "/articles/arduino-gbox-diy-review",
        )
        for path in paths:
            with self.subTest(path=path):
                status, content_type, body = self.get(path)
                self.assertEqual(status, 200)
                self.assertIn("text/html", content_type)
                self.assertIn('id="readContent"', body)
                self.assertIn('/static/app.js', body)

    def test_existing_static_assets_still_work(self):
        for path, expected_type in (
            ("/static/app.js", "application/javascript"),
            ("/static/app.css", "text/css"),
        ):
            with self.subTest(path=path):
                status, content_type, body = self.get(path)
                self.assertEqual(status, 200)
                self.assertIn(expected_type, content_type)
                self.assertTrue(body)

    def test_unrelated_unknown_route_remains_not_found(self):
        status, content_type, body = self.get("/unknown-page")
        self.assertEqual(status, 404)
        self.assertIn("application/json", content_type)
        self.assertIn("找不到資源", body)


if __name__ == "__main__":
    unittest.main()
