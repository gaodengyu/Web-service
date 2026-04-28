from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

import app as game_app

from test.tests.base import GameBuddyTestCase


class OrderWorkflowTests(GameBuddyTestCase):
    def test_create_order_uses_buddy_coin_payment_when_selected(self):
        detail = self.unique_text("buddy-coin-order")
        player_username = self.unique_text("player")
        player_password = "Player1234"

        with game_app.app.app_context():
            game_app.add_user(
                player_username,
                player_password,
                "player",
                email=f"{player_username}@example.com",
                profile={"buddy_coin_balance": 500.0, "buddy_coin_locked": 0.0},
            )
            assigned_booster = game_app.get_store_boosters(owner_username="club7_owner")[0]["username"]
            assigned_booster_user = game_app.get_user(assigned_booster)
            expected_price = game_app.calculate_time_based_quote(
                "2026-04-09T20:00",
                "2026-04-09T22:00",
                assigned_booster_user["profile"].get("price", ""),
            )["price"]

        login_response = self.login(player_username, player_password)
        self.assertEqual(login_response.status_code, 302)

        create_response = self.client.post(
            "/order/club7",
            data={
                "service_type": "技术上分",
                "game": "英雄联盟",
                "target_rank": "Gold to Platinum",
                "selected_booster": assigned_booster,
                "start_time": "2026-04-09T20:00",
                "end_time": "2026-04-09T22:00",
                "detail": detail,
                "payment_method": "buddy_coin",
            },
            follow_redirects=False,
        )

        self.assertEqual(create_response.status_code, 302)
        self.assertEqual(create_response.headers["Location"], "/player/orders")

        created_order = self.query_one(
            "SELECT * FROM orders WHERE detail = ? ORDER BY id DESC LIMIT 1",
            (detail,),
        )
        self.assertIsNotNone(created_order)
        self.assertEqual(created_order["payment_status"], "巴迪币已支付")
        self.assertEqual(created_order["status"], "待接待")
        self.assertEqual(created_order["price"], expected_price)

        with game_app.app.app_context():
            updated_user = game_app.get_user(player_username)
            wallet = game_app.get_wallet_snapshot(updated_user)
            self.assertAlmostEqual(wallet["balance"], 500.0 - float(expected_price), places=2)

    def test_payment_success_accepts_attribute_style_checkout_session(self):
        detail = self.unique_text("attribute-session-order")
        player_username = self.unique_text("player")
        player_password = "Player1234"

        with game_app.app.app_context():
            game_app.add_user(player_username, player_password, "player", email=f"{player_username}@example.com")

        login_response = self.login(player_username, player_password)
        self.assertEqual(login_response.status_code, 302)

        with patch.object(
            game_app.stripe.checkout.Session,
            "retrieve",
            return_value=SimpleNamespace(
                payment_status="paid",
                metadata={
                    "player": player_username,
                    "booster": "wayward",
                    "game": "英雄联盟",
                    "detail": detail,
                    "service_type": "技术上分",
                    "target_rank": "钻石",
                    "duration": "2 小时",
                    "preferred_time": "2026-04-09 20:00 - 22:00",
                    "price": "176",
                },
            ),
        ):
            response = self.client.get(
                "/payment-success",
                query_string={"session_id": "cs_attr_style_session"},
                follow_redirects=False,
            )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.headers["Location"], "/player/orders")

        created_order = self.query_one(
            "SELECT * FROM orders WHERE payment_session_id = ?",
            ("cs_attr_style_session",),
        )
        self.assertIsNotNone(created_order)
        self.assertEqual(created_order["detail"], detail)
        self.assertEqual(created_order["payment_status"], "已支付")

    def test_checkout_session_amount_is_recalculated_server_side(self):
        player_username = self.unique_text("player")
        player_password = "Player1234"

        with game_app.app.app_context():
            game_app.add_user(player_username, player_password, "player", email=f"{player_username}@example.com")
            booster_username = game_app.get_store_boosters(owner_username="club7_owner")[0]["username"]
            booster_user = game_app.get_user(booster_username)
            expected_total = game_app.calculate_time_based_quote(
                "2026-04-09T20:00",
                "2026-04-09T22:00",
                booster_user["profile"].get("price", ""),
            )["price"]

        self.login(player_username, player_password)

        captured_payload = {}

        def fake_checkout_create(**kwargs):
            captured_payload.update(kwargs)
            return SimpleNamespace(url="https://checkout.stripe.test/server-repriced")

        with patch.object(game_app, "stripe_is_configured", return_value=True), patch.object(
            game_app.stripe.checkout.Session,
            "create",
            side_effect=fake_checkout_create,
        ):
            response = self.client.post(
                "/create-checkout-session",
                json={
                    "product_name": "malicious-name",
                    "amount": "1",
                    "booster": booster_username,
                    "game": "英雄联盟",
                    "service_type": "技术上分",
                    "target_rank": "Gold to Platinum",
                    "detail": "server-side pricing check",
                    "start_time": "2026-04-09T20:00",
                    "end_time": "2026-04-09T22:00",
                },
                headers={"X-CSRF-Token": "test-csrf-token"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["checkout_url"], "https://checkout.stripe.test/server-repriced")
        self.assertEqual(captured_payload["line_items"][0]["price_data"]["unit_amount"], int(float(expected_total) * 100))
        self.assertEqual(captured_payload["line_items"][0]["price_data"]["product_data"]["name"], f"GameBuddy - {booster_username} 服务订单")

    def test_player_store_booster_admin_can_complete_the_core_order_lifecycle(self):
        detail = self.unique_text("automated-order-detail")
        player_username = self.unique_text("player")
        player_password = "Player1234"

        with game_app.app.app_context():
            game_app.add_user(player_username, player_password, "player", email=f"{player_username}@example.com")
            assigned_booster = game_app.get_store_boosters(owner_username="club7_owner")[0]["username"]
            target_store = game_app.get_store_by_slug("club7")
            assigned_booster_user = game_app.get_user(assigned_booster)
            expected_price = game_app.calculate_time_based_quote(
                "2026-04-09T20:00",
                "2026-04-09T22:00",
                assigned_booster_user["profile"].get("price", ""),
            )["price"]

        player_login = self.login(player_username, player_password)
        self.assertEqual(player_login.status_code, 302)

        session_id = "cs_test_order_workflow"
        with patch.object(game_app, "stripe_is_configured", return_value=True), patch.object(
            game_app.stripe.checkout.Session,
            "create",
            return_value=SimpleNamespace(url="https://checkout.stripe.test/session"),
        ), patch.object(
            game_app.stripe.checkout.Session,
            "retrieve",
            return_value={
                "payment_status": "paid",
                "metadata": {
                    "player": player_username,
                    "booster": "",
                    "store_id": str(target_store["id"]),
                    "store_owner": "club7_owner",
                    "store_name": target_store["name"],
                    "assigned_booster": "",
                    "assigned_booster_name": "",
                    "selected_booster": assigned_booster,
                    "selected_booster_name": assigned_booster,
                    "booster": assigned_booster,
                    "service_type": "技术上分",
                    "game": "英雄联盟",
                    "target_rank": "Gold to Platinum",
                    "duration": "2 小时",
                    "preferred_time": "2026-04-09 20:00 - 22:00",
                    "detail": detail,
                    "price": expected_price,
                },
            },
        ):
            create_response = self.client.post(
                "/order/club7",
                data={
                    "service_type": "技术上分",
                    "game": "英雄联盟",
                    "target_rank": "Gold to Platinum",
                    "selected_booster": assigned_booster,
                    "start_time": "2026-04-09T20:00",
                    "end_time": "2026-04-09T22:00",
                    "detail": detail,
                },
                follow_redirects=False,
            )
            self.assertEqual(create_response.status_code, 302)
            self.assertEqual(create_response.headers["Location"], "https://checkout.stripe.test/session")

            success_response = self.client.get(
                "/payment-success",
                query_string={"session_id": session_id},
                follow_redirects=False,
            )
            self.assertEqual(success_response.status_code, 302)
            self.assertEqual(success_response.headers["Location"], "/player/orders")

        created_order = self.query_one(
            "SELECT * FROM orders WHERE detail = ? ORDER BY id DESC LIMIT 1",
            (detail,),
        )
        self.assertIsNotNone(created_order)
        order_id = created_order["id"]
        self.assertEqual(created_order["status"], "待接待")
        self.assertEqual(created_order["payment_status"], "已支付")
        self.assertEqual(created_order["store_owner"], "club7_owner")
        self.assertEqual(created_order["booster"], assigned_booster)
        self.assertEqual(created_order["price"], expected_price)
        self.assertEqual(created_order["duration"], "2 小时")
        self.assertEqual(created_order["preferred_time"], "2026-04-09 20:00 - 22:00")

        order_amount = round(float(expected_price), 2)
        expected_booster_share = round(order_amount * game_app.BOOSTER_REVENUE_SHARE, 2)
        expected_merchant_share = round(order_amount - expected_booster_share, 2)
        with game_app.app.app_context():
            merchant_wallet_before = game_app.get_wallet_snapshot(game_app.get_user("club7_owner"))
            booster_wallet_before = game_app.get_wallet_snapshot(game_app.get_user(assigned_booster))

        self.logout()

        merchant_login = self.login("club7_owner", "12345678")
        self.assertEqual(merchant_login.status_code, 302)
        self.assertEqual(merchant_login.headers["Location"], "/merchant")

        assign_response = self.client.post(
            "/merchant",
            data={"order_id": order_id, "action": "assign_booster", "booster_username": assigned_booster},
            follow_redirects=False,
        )
        self.assertEqual(assign_response.status_code, 302)
        self.assertEqual(assign_response.headers["Location"], "/merchant")

        self.logout()

        booster_login = self.login(assigned_booster, "12345678")
        self.assertEqual(booster_login.status_code, 302)
        self.assertEqual(booster_login.headers["Location"], "/booster")

        finish_response = self.client.post(
            "/booster/orders",
            data={"order_id": order_id, "action": "finish"},
            follow_redirects=False,
        )
        self.assertEqual(finish_response.status_code, 302)
        self.assertEqual(finish_response.headers["Location"], "/booster/orders")

        self.logout()

        player_login_again = self.login(player_username, player_password)
        self.assertEqual(player_login_again.status_code, 302)
        self.assertEqual(player_login_again.headers["Location"], "/")

        confirm_response = self.client.post(
            "/player/orders",
            data={"order_id": order_id, "action": "confirm_complete"},
            follow_redirects=False,
        )
        self.assertEqual(confirm_response.status_code, 302)
        self.assertEqual(confirm_response.headers["Location"], "/player/orders")

        rate_response = self.client.post(
            "/player/orders",
            data={
                "order_id": order_id,
                "action": "rate",
                "rating": "5",
                "comment": "Helpful and on time.",
            },
            follow_redirects=False,
        )
        self.assertEqual(rate_response.status_code, 302)
        self.assertEqual(rate_response.headers["Location"], "/player/orders")

        complain_response = self.client.post(
            "/player/orders",
            data={
                "order_id": order_id,
                "action": "complain",
                "complaint": "Late follow-up after the session.",
            },
            follow_redirects=False,
        )
        self.assertEqual(complain_response.status_code, 302)
        self.assertEqual(complain_response.headers["Location"], "/player/orders")

        self.logout()

        admin_login = self.login("guanliyuan", "1234")
        self.assertEqual(admin_login.status_code, 302)
        self.assertEqual(admin_login.headers["Location"], "/admin")

        admin_response = self.client.post(
            "/admin/orders",
            data={
                "order_id": order_id,
                "action": "handle_complaint",
                "complaint_status": "已解决",
                "complaint_reply": "Admin reviewed the case and closed the complaint.",
                "admin_note": "Handled in automated testing.",
            },
            follow_redirects=False,
        )
        self.assertEqual(admin_response.status_code, 302)
        self.assertEqual(admin_response.headers["Location"], "/admin/orders")

        final_order = self.query_one("SELECT * FROM orders WHERE id = ?", (order_id,))
        self.assertEqual(final_order["status"], "已完成")
        self.assertEqual(final_order["payment_status"], "已支付")
        self.assertEqual(final_order["rating"], "5")
        self.assertEqual(final_order["comment"], "Helpful and on time.")
        self.assertEqual(final_order["complaint_status"], "已解决")
        self.assertEqual(final_order["complaint_reply"], "Admin reviewed the case and closed the complaint.")
        self.assertEqual(final_order["booster"], assigned_booster)
        self.assertEqual(final_order["assigned_booster"], assigned_booster)
        self.assertEqual(final_order["booster_coin_settled"], 1)

        with game_app.app.app_context():
            merchant_wallet_after = game_app.get_wallet_snapshot(game_app.get_user("club7_owner"))
            booster_wallet_after = game_app.get_wallet_snapshot(game_app.get_user(assigned_booster))

        self.assertAlmostEqual(
            merchant_wallet_after["balance"],
            merchant_wallet_before["balance"] + expected_merchant_share,
            places=2,
        )
        self.assertAlmostEqual(
            booster_wallet_after["balance"],
            booster_wallet_before["balance"] + expected_booster_share,
            places=2,
        )

        booster_notifications = self.query_one(
            "SELECT COUNT(*) AS c FROM messages WHERE receiver = ? AND type = ?",
            (assigned_booster, "notification"),
        )
        player_notifications = self.query_one(
            "SELECT COUNT(*) AS c FROM messages WHERE receiver = ? AND type = ?",
            (player_username, "notification"),
        )
        merchant_notifications = self.query_one(
            "SELECT COUNT(*) AS c FROM messages WHERE receiver = ? AND type = ?",
            ("club7_owner", "notification"),
        )
        self.assertGreater(booster_notifications["c"], 0)
        self.assertGreater(player_notifications["c"], 0)
        self.assertGreater(merchant_notifications["c"], 0)

    def test_rank_order_requires_target_rank(self):
        player_username = self.unique_text("player")
        player_password = "Player1234"

        with game_app.app.app_context():
            game_app.add_user(player_username, player_password, "player", email=f"{player_username}@example.com")
            assigned_booster = game_app.get_store_boosters(owner_username="club7_owner")[0]["username"]

        login_response = self.login(player_username, player_password)
        self.assertEqual(login_response.status_code, 302)

        create_response = self.client.post(
            "/order/club7",
            data={
                "service_type": "技术上分",
                "game": "英雄联盟",
                "target_rank": "",
                "selected_booster": assigned_booster,
                "start_time": "2026-04-09T20:00",
                "end_time": "2026-04-09T22:00",
                "detail": self.unique_text("missing-rank-detail"),
            },
            follow_redirects=False,
        )

        self.assertEqual(create_response.status_code, 302)
        self.assertEqual(create_response.headers["Location"], "/order/club7")
