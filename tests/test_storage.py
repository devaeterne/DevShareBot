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

    def test_request_routes_are_independent_and_persistent(self):
        with tempfile.TemporaryDirectory() as directory:
            path = str(Path(directory) / "db.sqlite3")
            store = RouteStore(path)
            store.save(-1001, -1002, ["analiz"], 42)
            self.assertIsNone(store.get_request(-1001))
            store.save_request(-1001, -1003, 42)
            store.save_request(-1004, -1005, 90)
            self.assertEqual(store.get_request(-1001).target_id, -1003)
            self.assertEqual(store.get(-1001).target_id, -1002)
            store.disable_request(-1001, 42)
            self.assertFalse(store.get_request(-1001).enabled)
            self.assertTrue(store.get_request(-1004).enabled)
            store.close()

            store = RouteStore(path)
            self.assertEqual(store.get_request(-1001).target_id, -1003)
            self.assertFalse(store.get_request(-1001).enabled)
            store.save_request(-1001, -1006, 42)
            self.assertTrue(store.get_request(-1001).enabled)
            self.assertEqual(store.get(-1001).target_id, -1002)
            store.close()

    def test_request_same_source_destination_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            store = RouteStore(str(Path(directory) / "db.sqlite3"))
            with self.assertRaises(ValueError):
                store.save_request(-1001, -1001, 42)
            store.close()


if __name__ == "__main__":
    unittest.main()
