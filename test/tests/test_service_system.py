from __future__ import annotations

from test.tests.base import GameBuddyTestCase


class ServiceSystemTests(GameBuddyTestCase):
    def test_service_frontend_shell_is_public(self):
        response = self.client.get("/service")

        self.assertEqual(response.status_code, 200)
        self.assertIn(b'id="service-app"', response.data)
        self.assertIn(b"/static/service-system/app.js", response.data)

    def test_service_bootstrap_exposes_contract(self):
        response = self.client.get("/api/bootstrap")

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["serviceRoutes"]["home"], "/service")
        self.assertIn("serviceTypeOptions", payload["constants"])

    def test_service_dashboard_requires_login(self):
        response = self.client.get("/api/dashboard")

        self.assertEqual(response.status_code, 401)
        payload = response.get_json()
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["error"]["code"], "unauthenticated")

    def test_service_api_login_unlocks_dashboard_snapshot(self):
        login_response = self.client.post(
            "/api/auth/login",
            json={"identifier": "Gdy233", "password": "yudenggao233"},
            headers={"X-CSRF-Token": "test-csrf-token"},
        )

        self.assertEqual(login_response.status_code, 200)
        login_payload = login_response.get_json()
        self.assertTrue(login_payload["ok"])
        self.assertEqual(login_payload["session"]["role"], "player")

        dashboard_response = self.client.get("/api/dashboard")
        self.assertEqual(dashboard_response.status_code, 200)

        dashboard_payload = dashboard_response.get_json()
        self.assertTrue(dashboard_payload["ok"])
        self.assertEqual(dashboard_payload["role"], "player")
        self.assertIn("orders", dashboard_payload)

    def test_service_store_discovery_returns_store_cards(self):
        response = self.client.get("/api/stores")

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertTrue(payload["ok"])
        self.assertIn("stores", payload)
        self.assertIsInstance(payload["stores"], list)
