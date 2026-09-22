import unittest

import server


class CoreLogicTests(unittest.TestCase):
    def test_normalize_english_ignores_case_and_punctuation(self):
        self.assertEqual(server.normalize_english("Hello, WORLD!"), "hello world")

    def test_chinese_answer_tokens_support_multiple_meanings(self):
        self.assertEqual(server.chinese_tokens("放弃；遗弃"), {"放弃", "遗弃"})

    def test_hint_reveals_letters_after_three_failures(self):
        early = server.make_hint("abandon", "abonden", 2)
        later = server.make_hint("abandon", "abonden", 4)
        self.assertEqual(early["pattern"], "_______")
        self.assertTrue(later["pattern"].startswith("ab"))
        self.assertIn(3, early["wrong_positions"])

    def test_hint_keeps_fully_revealed_last_letter(self):
        result = server.make_hint("abandon", "abonden", 9)
        self.assertEqual(result["pattern"], "abandon")

    def test_local_writing_score_is_percentage(self):
        essay = " ".join(["Learning changes our future."] * 45)
        result = server.local_writing_evaluation(essay)
        self.assertGreaterEqual(result["score"], 0)
        self.assertLessEqual(result["score"], 100)
        self.assertEqual(result["source"], "local")


if __name__ == "__main__":
    unittest.main()
