import json
import os
import tempfile
import threading
import unittest
from urllib.request import urlopen

import server


class VisitStatsTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.original_db_path = server.DB_PATH
        server.DB_PATH = os.path.join(self.temp_dir.name, "visit-stats.db")
        server.init_db()
        self.httpd = server.ThreadingHTTPServer(("127.0.0.1", 0), server.App)
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.thread.start()
        self.base_url = f"http://127.0.0.1:{self.httpd.server_port}"

    def tearDown(self):
        self.httpd.shutdown()
        self.httpd.server_close()
        self.thread.join(timeout=5)
        server.DB_PATH = self.original_db_path
        self.temp_dir.cleanup()

    def test_home_page_increments_existing_site_stats_value(self):
        with urlopen(self.base_url + "/", timeout=5) as response:
            self.assertEqual(response.status, 200)
        with urlopen(self.base_url + "/", timeout=5) as response:
            self.assertEqual(response.status, 200)
        with urlopen(self.base_url + "/api/visit-stats", timeout=5) as response:
            payload = json.loads(response.read().decode("utf-8"))

        self.assertTrue(payload["ok"])
        self.assertEqual(payload["visits"], 2)
        connection = server.db()
        try:
            row = connection.execute(
                "SELECT value FROM site_stats WHERE key = 'home_visits'"
            ).fetchone()
        finally:
            connection.close()
        self.assertEqual(row["value"], 2)


if __name__ == "__main__":
    unittest.main()
