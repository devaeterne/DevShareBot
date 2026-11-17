import unittest

from bot.filters import compile_hashtags, eligible_content, normalize_tags


class HashtagFilterTests(unittest.TestCase):
    def setUp(self):
        self.pattern = compile_hashtags("Analiz,Kar,Proje")

    def test_matches_case_insensitively(self):
        self.assertTrue(eligible_content("Yeni #analiz", None, self.pattern))
        self.assertTrue(eligible_content(None, "Bir #Proje", self.pattern))

    def test_turkish_dotted_i(self):
        tags = normalize_tags("#ANALİZ, #KAR, #PROJE")
        self.assertEqual(tags, ["analiz", "kar", "proje"])
        pattern = compile_hashtags(",".join(tags))
        self.assertTrue(eligible_content("#ANALİZ", None, pattern))
        self.assertTrue(eligible_content("#analiz", None, pattern))
        # Existing SQLite rows may have stored a decomposed capital-İ.
        old_saved = "anali\u0307z,kar,proje"
        self.assertTrue(eligible_content("#ANALİZ", None, compile_hashtags(old_saved)))

    def test_does_not_match_longer_hashtags(self):
        self.assertFalse(eligible_content("#Karar", None, self.pattern))
        self.assertFalse(eligible_content("#Proje2026", None, self.pattern))

    def test_does_not_match_plain_words(self):
        self.assertFalse(eligible_content("Analiz toplantısı", None, self.pattern))

    def test_rejects_empty_or_invalid_configuration(self):
        with self.assertRaises(ValueError):
            compile_hashtags(" , ")
        with self.assertRaises(ValueError):
            compile_hashtags("Analiz,hello world")

    def test_hashtag_boundaries(self):
        self.assertFalse(eligible_content("abc#Kar", None, self.pattern))
        self.assertTrue(eligible_content("(#Kar)", None, self.pattern))

    def test_normalization_deduplicates(self):
        self.assertEqual(normalize_tags("#ANALIZ,analiz,Kar"), ["analiz", "kar"])


if __name__ == "__main__":
    unittest.main()
