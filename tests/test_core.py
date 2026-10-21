import gc
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from sqlgame import core


class CoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        data = Path(self.temp.name)
        self.patcher = patch.multiple(core, DATA_DIR=data, GAME_DB=data / "progress.sqlite3", LAB_DB=data / "lab.sqlite3")
        self.patcher.start()
        core.initialize()

    def tearDown(self):
        self.patcher.stop()
        gc.collect()
        self.temp.cleanup()

    def test_all_authored_solutions_match_their_expected_results(self):
        for exercise in core.EXERCISES:
            with self.subTest(exercise=exercise["id"]):
                result = core.grade(exercise["id"], exercise["solution"])
                self.assertTrue(result["correct"], result)

    def test_learning_schema_exposes_foreign_key_relationships(self):
        shop = {table["name"]: table for table in core.schema("shop")}
        relations = shop["orders"]["foreign_keys"]
        self.assertEqual({(r["from_column"], r["to_table"]) for r in relations}, {("customer_id", "customers"), ("product_id", "products")})

    def test_ai_challenge_database_is_validated_persisted_and_gradable(self):
        solution = "SELECT books.title, authors.name FROM books JOIN authors ON books.author_id=authors.id"
        challenge = core.register_ai_challenge({
            "title": "Книги автора",
            "topic": "JOIN",
            "schema_sql": "CREATE TABLE authors(id INTEGER PRIMARY KEY, name TEXT); CREATE TABLE books(id INTEGER PRIMARY KEY, author_id INTEGER REFERENCES authors(id), title TEXT);",
            "seed_sql": "INSERT INTO authors VALUES (1,'Айзек Азимов'); INSERT INTO books VALUES (1,1,'Я, робот');",
            "task": "Покажи названия книг и имена авторов.",
            "hint": "Соедини книги и авторов по author_id.",
            "solution_sql": solution,
            "explanation": "JOIN объединяет книгу с её автором.",
        }, "JOIN", 2, "joins")
        self.assertTrue(core.grade(challenge["id"], solution)["correct"])
        self.assertEqual(core.run_query(challenge["id"], "SELECT COUNT(*) FROM books")["rows"], [[1]])
        self.assertEqual(core.exercise_details(challenge["id"])["schema"][1]["foreign_keys"][0]["to_table"], "authors")
        self.assertEqual(core.record_completion(challenge["id"], "practice", 5000, 2, True)["xp_gained"], 35)
        self.assertEqual(core.list_ai_challenges()[0]["id"], challenge["id"])

    def test_ai_schema_cannot_attach_or_write_outside_its_sandbox(self):
        with self.assertRaises(ValueError):
            core.register_ai_challenge({
                "title": "Unsafe", "task": "Test", "schema_sql": "ATTACH DATABASE 'outside.sqlite3' AS outside; CREATE TABLE t(id);",
                "seed_sql": "", "solution_sql": "SELECT 1",
            }, "SQL", 1)

    def test_grader_compares_rows_without_requiring_incidental_order(self):
        result = core.grade("s2", "SELECT DISTINCT city FROM customers")
        self.assertTrue(result["correct"], result)

    def test_learning_database_is_read_only(self):
        with self.assertRaises(ValueError):
            core.run_query("shop", "INSERT INTO products VALUES (99, 'Bad', 'Test', 1, 1)")
        self.assertEqual(len(core.run_query("shop", "SELECT * FROM products")["rows"]), 5)

    def test_lab_setup_persists_but_blocks_attach(self):
        setup = core.run_lab(core.lab_template(), "setup")
        self.assertEqual(setup["tables"][0]["name"], "events")
        result = core.run_lab("SELECT COUNT(*) FROM events")
        self.assertEqual(result["rows"], [[5]])
        checked = core.grade_lab("SELECT event_name FROM events WHERE duration_ms > 300", "SELECT event_name FROM events WHERE duration_ms > 300")
        self.assertTrue(checked["correct"])
        self.assertEqual(core.complete_lab_task("challenge-1", True)["xp_gained"], 30)
        self.assertEqual(core.complete_lab_task("challenge-1", True)["xp_gained"], 0)
        with self.assertRaises(ValueError):
            core.run_lab("ATTACH DATABASE ':memory:' AS outside")

    def test_progress_awards_xp_and_diminishing_repeat_reward(self):
        exercise = next(e for e in core.EXERCISES if e["id"] != core.daily_exercise()["id"])
        first = core.record_completion(exercise["id"], "practice", 1000, 1.2, True)
        repeat = core.record_completion(exercise["id"], "practice", 900, 1.1, True)
        self.assertGreater(first["xp_gained"], repeat["xp_gained"])
        self.assertEqual(core.dashboard()["profile"]["xp"], first["xp_gained"] + repeat["xp_gained"])


if __name__ == "__main__":
    unittest.main()
