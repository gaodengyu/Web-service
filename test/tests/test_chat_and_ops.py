from __future__ import annotations

import app as game_app

from test.tests.base import GameBuddyTestCase


class ChatAndOperationsTests(GameBuddyTestCase):
    def test_player_must_enter_store_reception_before_chatting_with_merchant(self):
        login_response = self.login("Gdy233", "yudenggao233")
        self.assertEqual(login_response.status_code, 302)
        self.assertEqual(login_response.headers["Location"], "/")

        blocked_response = self.client.get("/chat/club7_owner", follow_redirects=False)
        self.assertEqual(blocked_response.status_code, 302)
        self.assertEqual(blocked_response.headers["Location"], "/")

        contact_response = self.client.get("/store/club7/contact", follow_redirects=False)
        self.assertEqual(contact_response.status_code, 302)
        self.assertEqual(contact_response.headers["Location"], "/chat/club7_owner")

        allowed_response = self.client.get("/chat/club7_owner", follow_redirects=False)
        self.assertEqual(allowed_response.status_code, 200)
        self.assertIn(b"/order/club7", allowed_response.data)
        self.assertIn("下单".encode("utf-8"), allowed_response.data)

        message_text = self.unique_text("automated-chat-message")
        send_response = self.client.post(
            "/send_message",
            data={"receiver": "club7_owner", "message": message_text},
            follow_redirects=False,
        )
        self.assertEqual(send_response.status_code, 302)
        self.assertEqual(send_response.headers["Location"], "/chat/club7_owner")

        stored_message = self.query_one(
            "SELECT * FROM messages WHERE sender = ? AND receiver = ? AND type = ? AND message = ?",
            ("Gdy233", "club7_owner", "chat", message_text),
        )
        self.assertIsNotNone(stored_message)

    def test_store_review_and_admin_account_governance_work_together(self):
        booster_username = self.unique_text("managed-booster")
        with game_app.app.app_context():
            store = game_app.get_store_by_owner("club7_owner")
            game_app.add_user(
                booster_username,
                "12345678",
                "booster",
                profile={
                    "display_name": "治理测试陪玩",
                    "store_id": store["id"],
                    "store_slug": store["slug"],
                    "store_name": store["name"],
                    "managed_by": "club7_owner",
                    "approval_status": "approved",
                },
            )

        merchant_login = self.login("club7_owner", "12345678")
        self.assertEqual(merchant_login.status_code, 302)
        self.assertEqual(merchant_login.headers["Location"], "/merchant")

        store_name = self.unique_text("club7-store")
        merchant_response = self.client.post(
            "/merchant/store",
            data={
                "name": store_name,
                "slug": self.unique_text("club7-slug"),
                "tagline": "Automated testing tagline",
                "description": "Automated test update for store profile.",
                "games": "英雄联盟,无畏契约",
                "city": "Online",
                "min_price": "99",
                "theme": "rose",
                "badge": "测试店铺",
                "contact_note": "Automated support note",
                "action": "submit_for_review",
            },
            follow_redirects=False,
        )
        self.assertEqual(merchant_response.status_code, 302)
        self.assertEqual(merchant_response.headers["Location"], "/merchant/store")

        updated_store = self.query_one(
            "SELECT * FROM stores WHERE owner_username = ?",
            ("club7_owner",),
        )
        self.assertEqual(updated_store["name"], store_name)
        self.assertEqual(updated_store["approval_status"], "pending")

        self.logout()

        admin_login = self.login("guanliyuan", "1234")
        self.assertEqual(admin_login.status_code, 302)
        self.assertEqual(admin_login.headers["Location"], "/admin")

        approve_store_response = self.client.post(
            "/admin/users",
            data={"store_id": updated_store["id"], "action": "approve_store", "csrf_token": "test-csrf-token"},
            follow_redirects=False,
        )
        self.assertEqual(approve_store_response.status_code, 302)
        self.assertEqual(approve_store_response.headers["Location"], "/admin/users")

        approved_store = self.query_one("SELECT * FROM stores WHERE id = ?", (updated_store["id"],))
        self.assertEqual(approved_store["approval_status"], "approved")

        ban_response = self.client.post(
            "/admin/users",
            data={"username": booster_username, "action": "ban"},
            follow_redirects=False,
        )
        self.assertEqual(ban_response.status_code, 302)
        self.assertEqual(ban_response.headers["Location"], "/admin/users")

        self.logout()

        banned_login = self.login(booster_username, "12345678")
        self.assertEqual(banned_login.status_code, 302)
        self.assertEqual(banned_login.headers["Location"], "/login")

        admin_login_again = self.login("guanliyuan", "1234")
        self.assertEqual(admin_login_again.status_code, 302)
        self.assertEqual(admin_login_again.headers["Location"], "/admin")

        unban_response = self.client.post(
            "/admin/users",
            data={"username": booster_username, "action": "unban"},
            follow_redirects=False,
        )
        self.assertEqual(unban_response.status_code, 302)
        self.assertEqual(unban_response.headers["Location"], "/admin/users")

        reset_response = self.client.post(
            "/admin/users",
            data={
                "username": booster_username,
                "action": "reset_password",
                "new_password": "resetpass123",
            },
            follow_redirects=False,
        )
        self.assertEqual(reset_response.status_code, 302)
        self.assertEqual(reset_response.headers["Location"], "/admin/users")

        self.logout()

        reset_login = self.login(booster_username, "resetpass123")
        self.assertEqual(reset_login.status_code, 302)
        self.assertEqual(reset_login.headers["Location"], "/booster")
