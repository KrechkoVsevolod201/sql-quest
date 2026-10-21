import gc
import json
import tempfile
import threading
import unittest
import urllib.request
from pathlib import Path
from unittest.mock import patch
from http.server import ThreadingHTTPServer

import sql_game
from sqlgame import core


class HttpApiTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        data = Path(self.temp.name)
        self.patcher = patch.multiple(core, DATA_DIR=data, GAME_DB=data / "progress.sqlite3", LAB_DB=data / "lab.sqlite3")
        self.patcher.start()
        core.initialize()
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), sql_game.Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base = f"http://127.0.0.1:{self.server.server_port}"

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)
        self.patcher.stop()
        gc.collect()
        self.temp.cleanup()

    def test_home_dashboard_and_grading_endpoints(self):
        with urllib.request.urlopen(self.base + "/") as response:
            self.assertIn(b"SQL Quest", response.read())
        with urllib.request.urlopen(self.base + "/readable.css") as response:
            self.assertIn("no-store", response.headers.get("Cache-Control", ""))
        with urllib.request.urlopen(self.base + "/api/dashboard") as response:
            dashboard = json.loads(response.read())
        self.assertEqual(dashboard["exercise_count"], len(core.EXERCISES))
        request = urllib.request.Request(self.base + "/api/grade", data=json.dumps({"exercise_id": "s1", "sql": core.EXERCISES[0]["solution"]}).encode(), headers={"Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(request) as response:
            result = json.loads(response.read())
        self.assertTrue(result["correct"], result)
        setup = urllib.request.Request(self.base + "/api/lab", data=json.dumps({"mode": "setup", "sql": core.lab_template()}).encode(), headers={"Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(setup) as response:
            self.assertEqual(len(json.loads(response.read())["tables"]), 1)
        lab_grade = urllib.request.Request(self.base + "/api/lab/grade", data=json.dumps({"sql": "SELECT event_name FROM events WHERE duration_ms > 300", "solution": "SELECT event_name FROM events WHERE duration_ms > 300"}).encode(), headers={"Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(lab_grade) as response:
            self.assertTrue(json.loads(response.read())["correct"])
        settings = urllib.request.Request(self.base + "/api/ai/settings", data=json.dumps({"base_url": "http://localhost:1234/v1", "model": "local-instruct", "api_key": "local-secret"}).encode(), headers={"Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(settings) as response:
            saved = json.loads(response.read())
        self.assertTrue(saved["configured"])
        self.assertTrue(saved["api_key_set"])
        self.assertNotIn("api_key", saved)
        with urllib.request.urlopen(self.base + "/api/ai/settings") as response:
            self.assertEqual(json.loads(response.read())["model"], "local-instruct")

    def test_ai_challenge_api_creates_an_independent_database_and_checks_solution(self):
        payload = {
            "title": "Цветы и цены", "topic": "SELECT", "module_id": "select",
            "schema_sql": "CREATE TABLE flowers(id INTEGER PRIMARY KEY, name TEXT, price INTEGER);",
            "seed_sql": "INSERT INTO flowers VALUES (1,'Ирис',120),(2,'Роза',250);",
            "task": "Найди цветы дороже 150.", "hint": "Используй WHERE.",
            "solution_sql": "SELECT name FROM flowers WHERE price > 150", "explanation": "Фильтр оставляет розу.",
        }
        with patch("sql_game.ai.generate_challenge", side_effect=lambda mode, topic, difficulty: core.register_ai_challenge(payload, topic or "SELECT", difficulty, "select")):
            request = urllib.request.Request(self.base + "/api/ai/challenge", data=json.dumps({"mode": "topic", "topic": "SELECT", "difficulty": 1}).encode(), headers={"Content-Type": "application/json"}, method="POST")
            with urllib.request.urlopen(request) as response:
                challenge = json.loads(response.read())
        detail = json.loads(urllib.request.urlopen(self.base + f"/api/exercises/{challenge['id']}").read())
        self.assertTrue(detail["generated"])
        self.assertEqual(detail["schema"][0]["name"], "flowers")
        run = urllib.request.Request(self.base + "/api/run", data=json.dumps({"database": challenge["id"], "sql": payload["solution_sql"]}).encode(), headers={"Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(run) as response:
            self.assertEqual(json.loads(response.read())["rows"], [["Роза"]])
        grade = urllib.request.Request(self.base + "/api/grade", data=json.dumps({"exercise_id": challenge["id"], "sql": payload["solution_sql"]}).encode(), headers={"Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(grade) as response:
            self.assertTrue(json.loads(response.read())["correct"])


if __name__ == "__main__":
    unittest.main()
