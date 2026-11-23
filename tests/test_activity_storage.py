import sqlite3
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

from fastapi import HTTPException

import src.app as app


class ActivityStorageTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.database_path = Path(self.temp_dir.name) / "activities.sqlite"
        self.database_path_patch = patch.object(app, "DATABASE_PATH", self.database_path)
        self.database_path_patch.start()
        app.initialize_database()

    def tearDown(self):
        self.database_path_patch.stop()
        self.temp_dir.cleanup()

    def test_registration_persists_and_duplicate_is_rejected(self):
        email = "test-student@mergington.edu"

        app.signup_for_activity("Chess Club", email)
        app.initialize_database()

        self.assertIn(email, app.get_activities()["Chess Club"]["participants"])
        with self.assertRaises(HTTPException) as error:
            app.signup_for_activity("Chess Club", email)
        self.assertEqual(error.exception.status_code, 400)

    def test_concurrent_signups_cannot_exceed_activity_capacity(self):
        with closing(sqlite3.connect(self.database_path)) as connection, connection:
            connection.execute(
                "UPDATE activities SET max_participants = 3 WHERE name = ?",
                ("Chess Club",),
            )

        def signup(email):
            try:
                app.signup_for_activity("Chess Club", email)
            except HTTPException as error:
                return error.status_code
            return 200

        emails = ["first@mergington.edu", "second@mergington.edu"]
        with ThreadPoolExecutor(max_workers=2) as executor:
            statuses = list(executor.map(signup, emails))

        self.assertEqual(statuses.count(200), 1)
        self.assertEqual(statuses.count(400), 1)
        self.assertEqual(
            len(app.get_activities()["Chess Club"]["participants"]),
            3,
        )

    def test_unregister_removes_registration_from_persistent_storage(self):
        email = "test-student@mergington.edu"
        app.signup_for_activity("Chess Club", email)

        app.unregister_from_activity("Chess Club", email)
        app.initialize_database()

        self.assertNotIn(email, app.get_activities()["Chess Club"]["participants"])


if __name__ == "__main__":
    unittest.main()
