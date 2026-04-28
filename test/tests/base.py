from __future__ import annotations

import shutil
import sqlite3
import sys
import tempfile
import unittest
import uuid
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import app as game_app


class GameBuddyTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        game_app.app.config.update(TESTING=True)

    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.temp_db_path = Path(self.tempdir.name) / "data.db"
        shutil.copyfile(ROOT / "data.db", self.temp_db_path)

        self.original_database = game_app.DATABASE
        game_app.DATABASE = str(self.temp_db_path)
        with game_app.app.app_context():
            game_app.init_db()
            game_app.ensure_upload_dirs()
            self._normalize_test_credentials()
        self.client = game_app.app.test_client()
        self.client.environ_base["HTTP_X_CSRF_TOKEN"] = "test-csrf-token"

    def tearDown(self) -> None:
        game_app.DATABASE = self.original_database
        self.tempdir.cleanup()

    def login(self, username: str, password: str):
        if username == "guanliyuan" and game_app.ADMIN_REGISTER_PASSWORD:
            password = game_app.ADMIN_REGISTER_PASSWORD
        return self.client.post(
            "/login",
            data={"username": username, "pwd": password},
            follow_redirects=False,
        )

    def logout(self):
        return self.client.get("/logout", follow_redirects=False)

    def query_one(self, sql: str, params=()):
        conn = sqlite3.connect(self.temp_db_path)
        conn.row_factory = sqlite3.Row
        try:
            row = conn.execute(sql, params).fetchone()
            return row
        finally:
            conn.close()

    def query_all(self, sql: str, params=()):
        conn = sqlite3.connect(self.temp_db_path)
        conn.row_factory = sqlite3.Row
        try:
            rows = conn.execute(sql, params).fetchall()
            return rows
        finally:
            conn.close()

    def unique_text(self, prefix: str) -> str:
        return f"{prefix}-{uuid.uuid4().hex[:10]}"

    def _normalize_test_credentials(self) -> None:
        seed_credentials = {
            "Gdy233": "yudenggao233",
            "club7_owner": "12345678",
            "guanliyuan": game_app.ADMIN_REGISTER_PASSWORD or "1234",
        }

        for username, password in seed_credentials.items():
            if game_app.get_user(username):
                game_app.clear_failed_login_attempts(username, unlock_account=True)
                game_app.update_user(username, {"password": password, "banned": False})

        for booster in game_app.get_store_boosters(owner_username="club7_owner"):
            username = booster.get("username", "")
            if not username or not game_app.get_user(username):
                continue
            game_app.clear_failed_login_attempts(username, unlock_account=True)
            game_app.update_user(username, {"password": "12345678", "banned": False})
