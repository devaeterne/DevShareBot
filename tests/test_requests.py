import unittest

from bot.requests import parse_request


class RequestParserTests(unittest.TestCase):
    def test_valid_request(self):
        self.assertEqual(parse_request("#Talep XAUUSD"), (True, "XAUUSD"))
        self.assertEqual(parse_request("  #talep BTC için analiz"), (True, "BTC için analiz"))
        self.assertEqual(parse_request("#TALEP\nAltın"), (True, "Altın"))

    def test_missing_payload(self):
        self.assertEqual(parse_request("#Talep"), (True, ""))
        self.assertEqual(parse_request("#Talep   "), (True, ""))

    def test_other_messages(self):
        self.assertEqual(parse_request("#Analiz #Talep XAUUSD"), (False, ""))
        self.assertEqual(parse_request("#Talepler XAUUSD"), (False, ""))
        self.assertEqual(parse_request("Merhaba #Talep BTC"), (False, ""))
        self.assertEqual(parse_request(None), (False, ""))


if __name__ == "__main__":
    unittest.main()
