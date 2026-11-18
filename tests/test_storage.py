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

    def test_request_quota_and_configuration(self):
        with tempfile.TemporaryDirectory() as directory:
            store = RouteStore(str(Path(directory) / "db.sqlite3"))
            store.save_request(-1001, -1002, 11)
            route = store.get_request(-1001)
            self.assertEqual(route.daily_limit, 1)
            self.assertIsNone(route.start_minute)
            self.assertTrue(route.enabled)
            self.assertEqual(store.claim_request(-1001, 101, "2026-11-18", 10), "accepted")
            self.assertEqual(store.claim_request(-1001, 101, "2026-11-18", 10), "duplicate")
            self.assertEqual(store.claim_request(-1001, 101, "2026-11-18", 11), "limit")
            self.assertEqual(store.claim_request(-1001, 102, "2026-11-18", 12), "accepted")
            store.finish_request(-1001, 10, delivered=False)
            self.assertEqual(store.claim_request(-1001, 101, "2026-11-18", 11), "accepted")
            store.finish_request(-1001, 11, delivered=True)
            self.assertEqual(store.claim_request(-1001, 101, "2026-11-18", 13), "limit")
            self.assertEqual(store.claim_request(-1001, 101, "2026-11-19", 14), "accepted")
            store.set_request_limit(-1001, 2, 11)
            self.assertEqual(store.claim_request(-1001, 101, "2026-11-18", 15), "accepted")
            store.set_request_hours(-1001, 540, 1080, 11)
            self.assertEqual(store.get_request(-1001).start_minute, 540)
            store.set_request_enabled(-1001, False, 11)
            self.assertEqual(store.claim_request(-1001, 103, "2026-11-18", 16), "disabled")
            store.close()

    def test_request_settings_survive_restart_and_setup(self):
        with tempfile.TemporaryDirectory() as directory:
            path = str(Path(directory) / "db.sqlite3")
            store = RouteStore(path)
            store.save_request(-1001, -1002, 11)
            store.set_request_limit(-1001, 3, 11)
            store.set_request_hours(-1001, 1320, 120, 11)
            store.set_request_enabled(-1001, False, 11)
            store.close()
            store = RouteStore(path)
            route = store.get_request(-1001)
            self.assertEqual((route.daily_limit, route.start_minute, route.end_minute), (3, 1320, 120))
            self.assertFalse(route.enabled)
            store.save_request(-1001, -1003, 11)
            self.assertEqual(store.get_request(-1001).daily_limit, 3)
            self.assertEqual(store.get_request(-1001).target_id, -1003)
            store.close()

    def test_request_legacy_db_migration(self):
        import sqlite3
        with tempfile.TemporaryDirectory() as directory:
            path = str(Path(directory) / "db.sqlite3")
            db = sqlite3.connect(path)
            db.execute("""CREATE TABLE request_routes (
                source_id INTEGER PRIMARY KEY, target_id INTEGER NOT NULL,
                enabled INTEGER NOT NULL DEFAULT 1,
                updated_by INTEGER NOT NULL,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )""")
            db.execute("INSERT INTO request_routes(source_id,target_id,updated_by) VALUES (-1001,-1002,42)")
            db.commit()
            db.close()
            store = RouteStore(path)
            route = store.get_request(-1001)
            self.assertEqual((route.target_id, route.daily_limit, route.enabled), (-1002, 1, True))
            store.close()

    def test_request_same_source_destination_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            store = RouteStore(str(Path(directory) / "db.sqlite3"))
            with self.assertRaises(ValueError):
                store.save_request(-1001, -1001, 42)
            store.close()


if __name__ == "__main__":
    unittest.main()
