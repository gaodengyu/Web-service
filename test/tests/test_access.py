from __future__ import annotations

import json

import app as game_app

from test.tests.base import GameBuddyTestCase


class AccessControlTests(GameBuddyTestCase):
    def test_public_pages_return_http_200(self):
        for path in ["/", "/boosters", "/login", "/merchant-application-status"]:
            with self.subTest(path=path):
                response = self.client.get(path)
                self.assertEqual(response.status_code, 200)

    def test_protected_route_redirects_anonymous_users(self):
        response = self.client.get("/player", follow_redirects=False)
        self.assertEqual(response.status_code, 302)
        self.assertIn("/login", response.headers["Location"])

    def test_each_role_redirects_to_the_correct_dashboard_after_login(self):
        booster_username = self.unique_text("store-booster")
        with game_app.app.app_context():
            store = game_app.get_store_by_owner("club7_owner")
            game_app.add_user(
                booster_username,
                "12345678",
                "booster",
                profile={
                    "display_name": "测试陪玩师",
                    "store_id": store["id"],
                    "store_slug": store["slug"],
                    "store_name": store["name"],
                    "managed_by": "club7_owner",
                    "approval_status": "approved",
                },
            )
        cases = [
            ("Gdy233", "yudenggao233", "/"),
            (booster_username, "12345678", "/booster"),
            ("club7_owner", "12345678", "/merchant"),
            ("guanliyuan", "1234", "/admin"),
        ]
        for username, password, expected_location in cases:
            with self.subTest(username=username):
                response = self.login(username, password)
                self.assertEqual(response.status_code, 302)
                self.assertEqual(response.headers["Location"], expected_location)
                self.logout()

    def test_logged_in_non_players_are_redirected_from_discovery_pages(self):
        booster_username = self.unique_text("store-booster")
        unbound_booster_username = self.unique_text("unbound-booster")
        with game_app.app.app_context():
            store = game_app.get_store_by_owner("club7_owner")
            game_app.add_user(
                booster_username,
                "12345678",
                "booster",
                profile={
                    "display_name": "Store Booster",
                    "store_id": store["id"],
                    "store_slug": store["slug"],
                    "store_name": store["name"],
                    "managed_by": "club7_owner",
                    "approval_status": "approved",
                },
            )
            game_app.add_user(
                unbound_booster_username,
                "12345678",
                "booster",
                profile={
                    "display_name": "Unbound Booster",
                    "approval_status": "approved",
                },
            )

        cases = [
            (booster_username, "12345678", "/booster"),
            (unbound_booster_username, "12345678", "/booster/apply-store"),
            ("club7_owner", "12345678", "/merchant"),
            ("guanliyuan", "1234", "/admin"),
        ]
        for username, password, expected_location in cases:
            for path in ["/", "/boosters"]:
                with self.subTest(username=username, path=path):
                    self.login(username, password)
                    response = self.client.get(path, follow_redirects=False)
                    self.assertEqual(response.status_code, 302)
                    self.assertEqual(response.headers["Location"], expected_location)
                    self.logout()

    def test_anonymous_home_renders_auth_gateway(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertNotIn(b"/social-login/wechat", response.data)
        self.assertNotIn(b"/social-login/qq", response.data)
        self.assertIn(b'name="identifier"', response.data)
        self.assertNotIn("手机号登录".encode("utf-8"), response.data)
        self.assertNotIn("邮箱登录".encode("utf-8"), response.data)
        self.assertIn(">登录<".encode("utf-8"), response.data)

    def test_email_registration_redirects_to_role_selection_then_creates_user(self):
        username = self.unique_text("auth-user")
        email = f"{username}@example.com"
        phone = "13800138000"

        response = self.client.post(
            "/register",
            data={
                "email": email,
                "phone": phone,
                "username": username,
                "pwd": "secret123",
                "confirm_pwd": "secret123",
            },
            follow_redirects=False,
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.headers["Location"], "/choose-role")

        response = self.client.post(
            "/choose-role",
            data={"username": username, "email": email, "phone": phone, "role": "player"},
            follow_redirects=False,
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.headers["Location"], "/")

        user = self.query_one("SELECT username, role, email, phone FROM users WHERE username = ?", (username,))
        self.assertIsNotNone(user)
        self.assertEqual(user["role"], "player")
        self.assertEqual(user["email"], email)
        self.assertEqual(user["phone"], phone)

    def test_phone_login_accepts_bound_mobile_number(self):
        username = self.unique_text("phone-user")
        email = f"{username}@example.com"
        phone = "13900139000"

        response = self.client.post(
            "/register",
            data={
                "email": email,
                "phone": phone,
                "username": username,
                "pwd": "secret123",
                "confirm_pwd": "secret123",
            },
            follow_redirects=False,
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.headers["Location"], "/choose-role")

        response = self.client.post(
            "/choose-role",
            data={"username": username, "email": email, "phone": phone, "role": "player"},
            follow_redirects=False,
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.headers["Location"], "/")

        self.logout()

        response = self.client.post(
            "/login",
            data={"identifier": phone, "pwd": "secret123"},
            follow_redirects=False,
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.headers["Location"], "/")

    def test_social_login_route_redirects_back_to_login(self):
        response = self.client.get("/social-login/wechat", follow_redirects=False)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.headers["Location"], "/login")

        with self.client.session_transaction() as session:
            onboarding = session.get("auth_onboarding")

        self.assertIsNone(onboarding)

    def test_player_can_contact_store_and_unlock_store_chat(self):
        self.login("Gdy233", "yudenggao233")

        response = self.client.get("/store/club7/contact", follow_redirects=False)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.headers["Location"], "/chat/club7_owner")

        user = self.query_one("SELECT profile FROM users WHERE username = ?", ("Gdy233",))
        self.assertIsNotNone(user)
        profile = json.loads(user["profile"])
        self.assertIn("club7", profile.get("contacted_stores", []))

        chats = self.client.get("/player/chats")
        self.assertEqual(chats.status_code, 200)
        self.assertIn(b"/chat/club7_owner", chats.data)
        self.assertIn(b"/store/club7", chats.data)

    def test_merchant_can_see_players_who_contacted_store(self):
        self.login("Gdy233", "yudenggao233")
        self.client.get("/store/club7/contact", follow_redirects=False)
        self.logout()

        self.login("club7_owner", "12345678")
        response = self.client.get("/merchant/chats")

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Gdy233", response.data)
