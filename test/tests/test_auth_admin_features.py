from __future__ import annotations

import re
from io import BytesIO
from unittest.mock import patch

import app as game_app

from test.tests.base import GameBuddyTestCase


class AuthAndAdminFeatureTests(GameBuddyTestCase):
    def test_public_booster_registration_requires_admin_review_and_sends_email_on_approval(self):
        username = self.unique_text("public-booster")
        email = f"{username}@example.com"
        sent_mail = {}

        register_response = self.client.post(
            "/register",
            data={
                "email": email,
                "phone": "13800138110",
                "username": username,
                "pwd": "Booster123",
                "confirm_pwd": "Booster123",
                "csrf_token": "test-csrf-token",
            },
            follow_redirects=False,
        )
        self.assertEqual(register_response.status_code, 302)
        self.assertEqual(register_response.headers["Location"], "/choose-role")

        choose_role_response = self.client.post(
            "/choose-role",
            data={
                "role": "booster",
                "username": username,
                "email": email,
                "phone": "13800138110",
                "game_name": "英雄联盟",
                "game_id": "艾欧尼亚-99999",
                "rank": "王者",
                "proof_image": (BytesIO(b"fake-proof"), "proof.png"),
                "csrf_token": "test-csrf-token",
            },
            content_type="multipart/form-data",
            follow_redirects=False,
        )
        self.assertEqual(choose_role_response.status_code, 302)
        self.assertEqual(choose_role_response.headers["Location"], "/login")

        with game_app.app.app_context():
            self.assertIsNone(game_app.get_user(username))
            applications = game_app.get_booster_applications(status="pending")
            application = next(item for item in applications if item["username"] == username)
            self.assertEqual(application["store_name"], "")

        def fake_send_email(to_email, subject, body):
            sent_mail["to"] = to_email
            sent_mail["subject"] = subject
            sent_mail["body"] = body

        self.login("guanliyuan", "1234")
        with patch.object(game_app, "send_email_message", side_effect=fake_send_email):
            approve_response = self.client.post(
                "/admin/users",
                data={
                    "action": "approve_booster_application",
                    "application_id": str(application["id"]),
                    "review_note": "资料齐全，允许开通",
                    "csrf_token": "test-csrf-token",
                },
                follow_redirects=False,
            )

        self.assertEqual(approve_response.status_code, 302)
        self.assertEqual(approve_response.headers["Location"], "/admin/users")

        with game_app.app.app_context():
            booster_user = game_app.get_user(username)
            reviewed_application = game_app.get_booster_application(application["id"])

        self.assertIsNotNone(booster_user)
        self.assertEqual(booster_user["role"], "booster")
        self.assertEqual(booster_user["profile"].get("managed_by", ""), "")
        self.assertEqual(reviewed_application["status"], "approved")
        self.assertEqual(sent_mail["to"], email)

    def test_public_booster_registration_rejection_keeps_account_uncreated_and_sends_email(self):
        username = self.unique_text("public-booster-reject")
        email = f"{username}@example.com"
        sent_mail = {}

        self.client.post(
            "/register",
            data={
                "email": email,
                "phone": "13800138111",
                "username": username,
                "pwd": "Booster123",
                "confirm_pwd": "Booster123",
                "csrf_token": "test-csrf-token",
            },
            follow_redirects=False,
        )
        self.client.post(
            "/choose-role",
            data={
                "role": "booster",
                "username": username,
                "email": email,
                "phone": "13800138111",
                "game_name": "无畏契约",
                "game_id": "VAL-77777",
                "rank": "Immortal",
                "proof_image": (BytesIO(b"fake-proof"), "proof.png"),
                "csrf_token": "test-csrf-token",
            },
            content_type="multipart/form-data",
            follow_redirects=False,
        )

        with game_app.app.app_context():
            applications = game_app.get_booster_applications(status="pending")
            application = next(item for item in applications if item["username"] == username)

        def fake_send_email(to_email, subject, body):
            sent_mail["to"] = to_email
            sent_mail["subject"] = subject
            sent_mail["body"] = body

        self.login("guanliyuan", "1234")
        with patch.object(game_app, "send_email_message", side_effect=fake_send_email):
            reject_response = self.client.post(
                "/admin/users",
                data={
                    "action": "reject_booster_application",
                    "application_id": str(application["id"]),
                    "review_note": "段位截图无法识别",
                    "csrf_token": "test-csrf-token",
                },
                follow_redirects=False,
            )

        self.assertEqual(reject_response.status_code, 302)
        self.assertEqual(reject_response.headers["Location"], "/admin/users")

        with game_app.app.app_context():
            booster_user = game_app.get_user(username)
            reviewed_application = game_app.get_booster_application(application["id"])

        self.assertIsNone(booster_user)
        self.assertEqual(reviewed_application["status"], "rejected")
        self.assertEqual(reviewed_application["review_note"], "段位截图无法识别")
        self.assertEqual(sent_mail["to"], email)

    def test_merchant_registration_requires_admin_review_and_sends_email_on_approval(self):
        username = self.unique_text("merchant-pending")
        email = f"{username}@example.com"
        sent_mail = {}

        register_response = self.client.post(
            "/register",
            data={
                "email": email,
                "phone": "13800138088",
                "username": username,
                "pwd": "Merchant123",
                "confirm_pwd": "Merchant123",
                "csrf_token": "test-csrf-token",
            },
            follow_redirects=False,
        )
        self.assertEqual(register_response.status_code, 302)
        self.assertEqual(register_response.headers["Location"], "/choose-role")

        choose_role_response = self.client.post(
            "/choose-role",
            data={
                "role": "merchant",
                "username": username,
                "email": email,
                "phone": "13800138088",
                "store_name": "测试商家店铺",
                "store_city": "上海",
                "business_license": (BytesIO(b"fake-license"), "license.png"),
                "id_proof": (BytesIO(b"fake-id"), "id.png"),
                "csrf_token": "test-csrf-token",
            },
            content_type="multipart/form-data",
            follow_redirects=False,
        )
        self.assertEqual(choose_role_response.status_code, 302)
        self.assertEqual(choose_role_response.headers["Location"], "/login")

        with game_app.app.app_context():
            self.assertIsNone(game_app.get_user(username))
            applications = game_app.get_merchant_applications(status="pending")
            application = next(item for item in applications if item["username"] == username)
            self.assertEqual(application["store_name"], "测试商家店铺")

        def fake_send_email(to_email, subject, body):
            sent_mail["to"] = to_email
            sent_mail["subject"] = subject
            sent_mail["body"] = body

        self.login("guanliyuan", "1234")
        with patch.object(game_app, "send_email_message", side_effect=fake_send_email):
            approve_response = self.client.post(
                "/admin/users",
                data={
                    "action": "approve_merchant_application",
                    "merchant_application_id": str(application["id"]),
                    "review_note": "资质齐全，允许入驻",
                    "csrf_token": "test-csrf-token",
                },
                follow_redirects=False,
            )

        self.assertEqual(approve_response.status_code, 302)
        self.assertEqual(approve_response.headers["Location"], "/admin/users")

        with game_app.app.app_context():
            merchant_user = game_app.get_user(username)
            reviewed_application = game_app.get_merchant_application(application["id"])

        self.assertIsNotNone(merchant_user)
        self.assertEqual(merchant_user["role"], "merchant")
        self.assertEqual(reviewed_application["status"], "approved")
        self.assertEqual(sent_mail["to"], email)

    def test_merchant_registration_rejection_keeps_account_uncreated_and_sends_email(self):
        username = self.unique_text("merchant-reject")
        email = f"{username}@example.com"
        sent_mail = {}

        self.client.post(
            "/register",
            data={
                "email": email,
                "phone": "13800138089",
                "username": username,
                "pwd": "Merchant123",
                "confirm_pwd": "Merchant123",
                "csrf_token": "test-csrf-token",
            },
            follow_redirects=False,
        )
        self.client.post(
            "/choose-role",
            data={
                "role": "merchant",
                "username": username,
                "email": email,
                "phone": "13800138089",
                "store_name": "待驳回商家",
                "store_city": "广州",
                "business_license": (BytesIO(b"fake-license"), "license.png"),
                "id_proof": (BytesIO(b"fake-id"), "id.png"),
                "csrf_token": "test-csrf-token",
            },
            content_type="multipart/form-data",
            follow_redirects=False,
        )

        with game_app.app.app_context():
            applications = game_app.get_merchant_applications(status="pending")
            application = next(item for item in applications if item["username"] == username)

        def fake_send_email(to_email, subject, body):
            sent_mail["to"] = to_email
            sent_mail["subject"] = subject
            sent_mail["body"] = body

        self.login("guanliyuan", "1234")
        with patch.object(game_app, "send_email_message", side_effect=fake_send_email):
            reject_response = self.client.post(
                "/admin/users",
                data={
                    "action": "reject_merchant_application",
                    "merchant_application_id": str(application["id"]),
                    "review_note": "资质图片不清晰",
                    "csrf_token": "test-csrf-token",
                },
                follow_redirects=False,
            )

        self.assertEqual(reject_response.status_code, 302)
        self.assertEqual(reject_response.headers["Location"], "/admin/users")

        with game_app.app.app_context():
            merchant_user = game_app.get_user(username)
            reviewed_application = game_app.get_merchant_application(application["id"])

        self.assertIsNone(merchant_user)
        self.assertEqual(reviewed_application["status"], "rejected")
        self.assertEqual(reviewed_application["review_note"], "资质图片不清晰")
        self.assertEqual(sent_mail["to"], email)

    def test_merchant_can_query_application_status_page(self):
        username = self.unique_text("merchant-status")
        email = f"{username}@example.com"

        self.client.post(
            "/register",
            data={
                "email": email,
                "phone": "13800138100",
                "username": username,
                "pwd": "Merchant123",
                "confirm_pwd": "Merchant123",
                "csrf_token": "test-csrf-token",
            },
            follow_redirects=False,
        )
        self.client.post(
            "/choose-role",
            data={
                "role": "merchant",
                "username": username,
                "email": email,
                "phone": "13800138100",
                "store_name": "状态查询店铺",
                "store_city": "深圳",
                "business_license": (BytesIO(b"fake-license"), "license.png"),
                "id_proof": (BytesIO(b"fake-id"), "id.png"),
                "csrf_token": "test-csrf-token",
            },
            content_type="multipart/form-data",
            follow_redirects=False,
        )

        query_response = self.client.post(
            "/merchant-application-status",
            data={
                "username": username,
                "email": email,
                "csrf_token": "test-csrf-token",
            },
            follow_redirects=True,
        )
        self.assertEqual(query_response.status_code, 200)
        self.assertIn(username.encode("utf-8"), query_response.data)
        self.assertIn("审核中".encode("utf-8"), query_response.data)

    def test_pending_merchant_without_email_can_query_status_from_login(self):
        username = self.unique_text("merchant-no-email")
        password = "Merchant123"

        register_response = self.client.post(
            "/register",
            data={
                "email": "",
                "phone": "13800138121",
                "username": username,
                "pwd": password,
                "confirm_pwd": password,
                "csrf_token": "test-csrf-token",
            },
            follow_redirects=False,
        )
        self.assertEqual(register_response.status_code, 302)
        self.assertEqual(register_response.headers["Location"], "/choose-role")

        self.client.post(
            "/choose-role",
            data={
                "role": "merchant",
                "username": username,
                "email": "",
                "phone": "13800138121",
                "store_name": "无邮箱商家",
                "store_city": "杭州",
                "business_license": (BytesIO(b"fake-license"), "license.png"),
                "id_proof": (BytesIO(b"fake-id"), "id.png"),
                "csrf_token": "test-csrf-token",
            },
            content_type="multipart/form-data",
            follow_redirects=False,
        )

        with game_app.app.app_context():
            application = game_app.find_latest_merchant_application_by_username(username)
            self.assertIsNotNone(application)
            self.assertEqual(application["email"], "")

        login_response = self.client.post(
            "/login",
            data={"username": username, "pwd": password},
            follow_redirects=False,
        )
        self.assertEqual(login_response.status_code, 302)
        self.assertIn("/merchant-application-status", login_response.headers["Location"])

        status_response = self.client.get(login_response.headers["Location"], follow_redirects=True)
        self.assertEqual(status_response.status_code, 200)
        self.assertIn("审核中".encode("utf-8"), status_response.data)

        self.login("guanliyuan", "1234")
        self.client.post(
            "/admin/users",
            data={
                "action": "reject_merchant_application",
                "merchant_application_id": str(application["id"]),
                "review_note": "资质不符合要求",
                "csrf_token": "test-csrf-token",
            },
            follow_redirects=False,
        )
        self.logout()

        rejected_login_response = self.client.post(
            "/login",
            data={"username": username, "pwd": password},
            follow_redirects=True,
        )
        self.assertEqual(rejected_login_response.status_code, 200)
        self.assertIn("审核失败账号已注销".encode("utf-8"), rejected_login_response.data)

    def test_pending_booster_without_email_can_query_status_from_login(self):
        username = self.unique_text("booster-no-email")
        password = "Booster123"

        self.client.post(
            "/register",
            data={
                "email": "",
                "phone": "13800138122",
                "username": username,
                "pwd": password,
                "confirm_pwd": password,
                "csrf_token": "test-csrf-token",
            },
            follow_redirects=False,
        )
        self.client.post(
            "/choose-role",
            data={
                "role": "booster",
                "username": username,
                "email": "",
                "phone": "13800138122",
                "game_name": "英雄联盟",
                "game_id": "峡谷-1024",
                "rank": "钻石",
                "proof_image": (BytesIO(b"fake-proof"), "proof.png"),
                "csrf_token": "test-csrf-token",
            },
            content_type="multipart/form-data",
            follow_redirects=False,
        )

        login_response = self.client.post(
            "/login",
            data={"username": username, "pwd": password},
            follow_redirects=False,
        )
        self.assertEqual(login_response.status_code, 302)
        self.assertIn("/merchant-application-status", login_response.headers["Location"])

        status_response = self.client.get(login_response.headers["Location"], follow_redirects=True)
        self.assertEqual(status_response.status_code, 200)
        self.assertIn("审核中".encode("utf-8"), status_response.data)

    def test_five_failed_logins_lock_the_account(self):
        username = self.unique_text("lock-user")
        with game_app.app.app_context():
            game_app.add_user(username, "StrongPass123", "player", email=f"{username}@example.com")

        for _ in range(5):
            response = self.client.post(
                "/login",
                data={"username": username, "pwd": "wrong-password"},
                follow_redirects=True,
            )

        self.assertEqual(response.status_code, 200)

        with game_app.app.app_context():
            user = game_app.get_user(username)

        self.assertIsNotNone(user)
        self.assertTrue(user["banned"])
        self.assertEqual(user["failed_login_attempts"], 5)
        self.assertEqual(user["lock_reason"], "too_many_failed_password_attempts")

    def test_forgot_password_resets_password_and_unlocks_account(self):
        username = self.unique_text("recover-user")
        email = f"{username}@example.com"
        old_password = "StrongPass123"
        new_password = "Recovered123"
        sent_mail = {}

        with game_app.app.app_context():
            game_app.add_user(username, old_password, "player", email=email, profile={"email": email})
            game_app.update_user(
                username,
                {
                    "banned": True,
                    "profile": {
                        "email": email,
                        "failed_login_attempts": 5,
                        "lock_reason": "too_many_failed_password_attempts",
                    },
                },
            )

        def fake_send_email(to_email, subject, body):
            sent_mail["to"] = to_email
            sent_mail["subject"] = subject
            sent_mail["body"] = body

        with patch.object(game_app, "mail_is_configured", return_value=True), patch.object(
            game_app, "send_email_message", side_effect=fake_send_email
        ):
            response = self.client.post(
                "/forgot-password",
                data={
                    "action": "send_code",
                    "username": username,
                    "email": email,
                    "csrf_token": "test-csrf-token",
                },
                follow_redirects=True,
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(sent_mail["to"], email)
        verification_match = re.search(r"(\d{6})", sent_mail["body"])
        self.assertIsNotNone(verification_match)
        verification_code = verification_match.group(1)

        reset_response = self.client.post(
            "/forgot-password",
            data={
                "action": "reset_password",
                "username": username,
                "email": email,
                "verification_code": verification_code,
                "new_password": new_password,
                "confirm_password": new_password,
                "csrf_token": "test-csrf-token",
            },
            follow_redirects=False,
        )

        self.assertEqual(reset_response.status_code, 302)
        self.assertEqual(reset_response.headers["Location"], "/login")

        login_response = self.client.post(
            "/login",
            data={"username": username, "pwd": new_password},
            follow_redirects=False,
        )
        self.assertEqual(login_response.status_code, 302)
        self.assertEqual(login_response.headers["Location"], "/")

        with game_app.app.app_context():
            user = game_app.get_user(username)

        self.assertIsNotNone(user)
        self.assertFalse(user["banned"])
        self.assertEqual(user["failed_login_attempts"], 0)
        self.assertEqual(user["email"], email)

    def test_merchant_submitted_booster_application_waits_for_admin_approval(self):
        username = self.unique_text("pending-booster")
        email = f"{username}@example.com"
        sent_mail = {}

        merchant_login = self.login("club7_owner", "12345678")
        self.assertEqual(merchant_login.status_code, 302)
        self.assertEqual(merchant_login.headers["Location"], "/merchant")

        application_response = self.client.post(
            "/merchant/talents",
            data={
                "action": "submit_application",
                "username": username,
                "password": "Booster123",
                "display_name": "测试陪玩",
                "email": email,
                "phone": "13800138001",
                "game_account": "峡谷之巅-123456",
                "games": "英雄联盟",
                "rank": "王者 80 星",
                "price": "99",
                "available_time": "每天 20:00 - 24:00",
                "play_style": "双排上分",
                "intro": "自动化测试提交的店内陪玩师。",
                "proof_image": (BytesIO(b"fake-image-data"), "proof.png"),
            },
            content_type="multipart/form-data",
            follow_redirects=False,
        )
        self.assertEqual(application_response.status_code, 302)
        self.assertEqual(application_response.headers["Location"], "/merchant/talents")

        with game_app.app.app_context():
            self.assertIsNone(game_app.get_user(username))
            applications = game_app.get_booster_applications(status="pending")
            application = next(item for item in applications if item["username"] == username)
            self.assertEqual(application["store_owner_username"], "club7_owner")
            self.assertEqual(application["store_name"], game_app.get_store_by_owner("club7_owner")["name"])

        def fake_send_email(to_email, subject, body):
            sent_mail["to"] = to_email
            sent_mail["subject"] = subject
            sent_mail["body"] = body

        self.logout()
        self.login("guanliyuan", "1234")
        with patch.object(game_app, "send_email_message", side_effect=fake_send_email):
            approve_response = self.client.post(
                "/admin/users",
                data={
                    "action": "approve_booster_application",
                    "application_id": str(application["id"]),
                    "review_note": "资料完整，允许开通店内陪玩师账号",
                    "csrf_token": "test-csrf-token",
                },
                follow_redirects=False,
            )

        self.assertEqual(approve_response.status_code, 302)
        self.assertEqual(approve_response.headers["Location"], "/admin/users")

        with game_app.app.app_context():
            approved_user = game_app.get_user(username)
            approved_application = game_app.get_booster_application(application["id"])

        self.assertIsNotNone(approved_user)
        self.assertEqual(approved_user["role"], "booster")
        self.assertEqual(approved_user["profile"]["managed_by"], "club7_owner")
        self.assertEqual(approved_user["profile"]["approval_status"], "approved")
        self.assertEqual(approved_application["status"], "approved")
        self.assertEqual(sent_mail["to"], email)

    def test_admin_can_reject_store_submitted_booster_application_without_creating_user(self):
        username = self.unique_text("reject-booster")
        email = f"{username}@example.com"
        sent_mail = {}

        self.login("club7_owner", "12345678")
        self.client.post(
            "/merchant/talents",
            data={
                "action": "submit_application",
                "username": username,
                "password": "Booster123",
                "display_name": "待驳回陪玩",
                "email": email,
                "phone": "13800138002",
                "game_account": "电一-654321",
                "games": "无畏契约",
                "rank": "Immortal 3",
                "proof_image": (BytesIO(b"fake-image-data"), "proof.png"),
            },
            content_type="multipart/form-data",
            follow_redirects=False,
        )

        with game_app.app.app_context():
            applications = game_app.get_booster_applications(status="pending")
            application = next(item for item in applications if item["username"] == username)

        def fake_send_email(to_email, subject, body):
            sent_mail["to"] = to_email
            sent_mail["subject"] = subject
            sent_mail["body"] = body

        self.logout()
        self.login("guanliyuan", "1234")
        with patch.object(game_app, "send_email_message", side_effect=fake_send_email):
            reject_response = self.client.post(
                "/admin/users",
                data={
                    "action": "reject_booster_application",
                    "application_id": str(application["id"]),
                    "review_note": "截图信息不清晰",
                    "csrf_token": "test-csrf-token",
                },
                follow_redirects=False,
            )

        self.assertEqual(reject_response.status_code, 302)
        self.assertEqual(reject_response.headers["Location"], "/admin/users")

        with game_app.app.app_context():
            user = game_app.get_user(username)
            reviewed_application = game_app.get_booster_application(application["id"])

        self.assertIsNone(user)
        self.assertEqual(reviewed_application["status"], "rejected")
        self.assertEqual(reviewed_application["review_note"], "截图信息不清晰")
        self.assertEqual(sent_mail["to"], email)
