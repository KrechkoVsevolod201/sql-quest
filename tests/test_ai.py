import unittest
from unittest.mock import patch

from sqlgame import ai


class AiReviewTests(unittest.TestCase):
    @patch("sqlgame.ai._chat", return_value="Запрос корректен. Можно добавить ORDER BY, чтобы результат был стабильным.")
    def test_review_keeps_plain_text_from_models_that_ignore_json_mode(self, _chat):
        review = ai.review("Отсортируй товары", "SELECT name FROM products")
        self.assertIn("Запрос корректен", review["verdict"])
        self.assertIsNone(review["score"])
        self.assertEqual(review["strengths"], [])

    @patch("sqlgame.ai._chat", return_value='Вот мой разбор:\n```json\n{"score":"84", "verdict":"Хорошее решение", "strengths":"JOIN использован верно", "suggestions":null, "next_hint":"Добавь фильтр"}\n```')
    def test_review_extracts_json_and_normalizes_optional_fields(self, _chat):
        review = ai.review("Задание", "SELECT 1")
        self.assertEqual(review["score"], 84)
        self.assertEqual(review["strengths"], ["JOIN использован верно"])
        self.assertEqual(review["suggestions"], [])
        self.assertEqual(review["next_hint"], "Добавь фильтр")

    @patch("sqlgame.ai._chat", return_value='{"rating": 72, "assessment": "Есть замечания к фильтру"}')
    def test_review_keeps_unrecognized_json_fields_visible(self, _chat):
        review = ai.review("Задание", "SELECT 1")
        self.assertEqual(review["score"], 72)
        self.assertIn("Есть замечания к фильтру", review["verdict"])


if __name__ == "__main__":
    unittest.main()
