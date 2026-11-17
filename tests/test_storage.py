import tempfile
import unittest
from pathlib import Path

from bot.storage import RouteStore


class RouteStoreTests(unittest.TestCase):
    def test_save_update_and_disable_persist(self):
        with tempfile.TemporaryDirectory() as directory:
            path = str(Path(directory) / "db.sqlite3")
            store = RouteStore(path)
            self.assertIsNone(store.get(-1001))
            store.save(-1001, -1002, ["analiz", "kar"], 42)
            store.save(-1003, -1004, ["proje"], 88)
            self.assertEqual(store.get(-1001).target_id, -1002)
            self.assertEqual(store.get(-1003).tags, ("proje",))
            store.set_tags(-1001, ["new"], 42)
            store.disable(-1001, 42)
            store.close()
            store = RouteStore(path)
            self.assertFalse(store.get(-1001).enabled)
            self.assertEqual(store.get(-1001).tags, ("new",))
            self.assertTrue(store.get(-1003).enabled)
            store.save(-1001, -1005, ["again"], 42)
            self.assertEqual(store.get(-1001).target_id, -1005)
            self.assertTrue(store.get(-1001).enabled)
            store.close()


if __name__ == "__main__":
    unittest.main()
