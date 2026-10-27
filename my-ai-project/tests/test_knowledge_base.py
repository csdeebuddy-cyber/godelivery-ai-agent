import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.main import app
from app.api.admin import _session_signer
from app.config import settings
from app.api.v1.endpoints.live import _live_config
from app.services.knowledge_base import (
    get_knowledge_base_context,
    get_knowledge_base_status,
    search_knowledge_base,
)


class KnowledgeBaseTests(unittest.TestCase):
    def test_customer_and_admin_routes_are_available(self) -> None:
        client = TestClient(app)

        root_response = client.get("/", follow_redirects=False)
        chat_response = client.get("/chatandshop")
        login_response = client.get("/dashboard/admin/login")
        admin_response = client.get("/dashboard/admin", follow_redirects=False)
        api_response = client.get("/api/v1/admin/status")
        robots_response = client.get("/robots.txt")

        self.assertEqual(root_response.status_code, 307)
        self.assertEqual(root_response.headers["location"], "/chatandshop")
        self.assertIn("noindex", root_response.headers["x-robots-tag"])
        self.assertEqual(chat_response.status_code, 200)
        self.assertIn("/dashboard/admin", chat_response.text)
        self.assertIn('name="googlebot" content="noindex', chat_response.text)
        self.assertEqual(login_response.status_code, 200)
        self.assertIn("smpmfast@gmail.com", login_response.text)
        self.assertIn('name="robots" content="noindex', login_response.text)
        self.assertEqual(admin_response.status_code, 303)
        self.assertEqual(admin_response.headers["location"], "/dashboard/admin/login")
        self.assertIn("noindex", admin_response.headers["x-robots-tag"])
        self.assertIn("noindex", api_response.headers["x-robots-tag"])
        self.assertEqual(robots_response.status_code, 200)
        self.assertIn("Allow: /", robots_response.text)
        self.assertNotIn("Disallow: /", robots_response.text)

    def test_admin_session_requires_allowed_email_and_disables_unconfigured_storage(self) -> None:
        client = TestClient(app)
        test_secret = "test-admin-session-secret-at-least-32-characters"

        with patch.object(settings, "ADMIN_SESSION_SECRET", test_secret):
            allowed_cookie = _session_signer().dumps({"email": "smpmfast@gmail.com"})
            client.cookies.set("godelivery_admin_session", allowed_cookie)
            overview_response = client.get("/api/v1/admin/overview")
            self.assertEqual(overview_response.status_code, 200)
            self.assertEqual(overview_response.json()["admin_email"], "smpmfast@gmail.com")
            self.assertFalse(overview_response.json()["storage"]["editing_enabled"])

            other_user_cookie = _session_signer().dumps({"email": "other@example.com"})
            client.cookies.set("godelivery_admin_session", other_user_cookie)
            denied_response = client.get("/api/v1/admin/overview")
            self.assertEqual(denied_response.status_code, 401)

    def test_admin_status_exposes_sso_setup_without_credentials(self) -> None:
        client = TestClient(app)
        with (
            patch.object(settings, "ADMIN_GOOGLE_CLIENT_ID", None),
            patch.object(settings, "ADMIN_GOOGLE_CLIENT_SECRET", None),
            patch.object(settings, "ADMIN_OAUTH_REDIRECT_URI", None),
            patch.object(settings, "ADMIN_SESSION_SECRET", None),
        ):
            status = client.get("/api/v1/admin/status")
            login = client.get("/admin/auth/google/login")

        self.assertEqual(status.status_code, 200)
        self.assertFalse(status.json()["sso_configured"])
        self.assertFalse(status.json()["storage"]["editing_enabled"])
        self.assertEqual(login.status_code, 503)
        self.assertEqual(login.json()["detail"]["code"], "google_sso_not_configured")

    def test_google_sign_in_start_uses_pkce_and_signed_state_cookie(self) -> None:
        client = TestClient(app)
        with (
            patch.object(settings, "ADMIN_GOOGLE_CLIENT_ID", "test-client-id"),
            patch.object(settings, "ADMIN_GOOGLE_CLIENT_SECRET", "test-client-secret"),
            patch.object(settings, "ADMIN_OAUTH_REDIRECT_URI", "http://testserver/admin/auth/google/callback"),
            patch.object(settings, "ADMIN_SESSION_SECRET", "test-admin-session-secret-at-least-32-characters"),
        ):
            response = client.get("/admin/auth/google/login", follow_redirects=False)

        self.assertEqual(response.status_code, 302)
        self.assertIn("code_challenge_method=S256", response.headers["location"])
        self.assertIn("code_challenge=", response.headers["location"])
        self.assertIn("godelivery_admin_oauth_state", response.headers["set-cookie"])

    def test_status_reports_unverified_catalog_and_no_active_promotions(self) -> None:
        status = get_knowledge_base_status()

        self.assertEqual(status["products"], 1)
        self.assertEqual(status["verified_products"], 0)
        self.assertEqual(status["active_promotions"], 0)

    def test_product_price_search_does_not_invent_price(self) -> None:
        result = search_knowledge_base("ราคา ALLDAY น้ำมันงาดำ")

        self.assertEqual(len(result["products"]), 1)
        self.assertIsNone(result["products"][0]["regular_price_thb"])
        self.assertIsNone(result["products"][0]["promotion_price_thb"])
        self.assertFalse(result["products"][0]["verified"])

    def test_promotion_search_explicitly_reports_unverified_promotion(self) -> None:
        result = search_knowledge_base("มีโปรโมชันไหม")

        self.assertEqual(result["promotions"], [])
        self.assertIsNotNone(result["promotion_status"])

    def test_policy_search_returns_relevant_document(self) -> None:
        result = search_knowledge_base("ขอทราบนโยบายคืนเงิน")

        self.assertEqual(len(result["policies"]), 1)
        self.assertIn("shipping_returns.md", result["policies"][0]["source"])

    def test_live_context_contains_only_catalog_and_promotion_data(self) -> None:
        context = get_knowledge_base_context()

        self.assertEqual(len(context["products"]), 1)
        self.assertEqual(context["promotions"], [])
        self.assertIsNone(context["products"][0]["regular_price_thb"])
        self.assertIn(
            "02_ordering_fulfillment/ordering.md",
            {document["source"] for document in context["documents"]},
        )

    def test_live_config_includes_local_knowledge_data_without_tools(self) -> None:
        config = _live_config("th-TH")

        self.assertIsNone(config.tools)
        self.assertIn("Current local knowledge-base data", config.system_instruction)

    def test_knowledge_api_exposes_search_and_status(self) -> None:
        client = TestClient(app)

        status_response = client.get("/api/v1/knowledge/status")
        products_response = client.get("/api/v1/knowledge/products")
        promotions_response = client.get("/api/v1/knowledge/promotions")
        search_response = client.get("/api/v1/knowledge/search", params={"q": "ราคา ALLDAY"})

        self.assertEqual(status_response.status_code, 200)
        self.assertEqual(products_response.status_code, 200)
        self.assertEqual(promotions_response.status_code, 200)
        self.assertEqual(search_response.status_code, 200)
        self.assertEqual(
            products_response.json()["products"],
            get_knowledge_base_context()["products"],
        )
        self.assertEqual(promotions_response.json()["promotions"], [])
        self.assertEqual(search_response.json()["products"][0]["name"], get_knowledge_base_context()["products"][0]["name"])

    def test_google_sheets_integration_is_explicitly_unconfigured(self) -> None:
        client = TestClient(app)

        status_response = client.get("/api/v1/integrations/status")
        sync_response = client.post("/api/v1/integrations/google-sheets/sync")

        self.assertEqual(status_response.status_code, 200)
        integration = status_response.json()["integrations"][0]
        self.assertEqual(integration["provider"], "google_sheets")
        self.assertFalse(integration["configured"])
        self.assertEqual(sync_response.status_code, 501)
        self.assertEqual(sync_response.json()["detail"]["code"], "integration_not_configured")

    def test_product_import_preview_accepts_example_but_does_not_persist_claims(self) -> None:
        client = TestClient(app)
        product = {
            "id": "PROD-001",
            "name": "งาดำสกัดเย็น",
            "category": "Dietary Supplement",
            "price_regular": 390,
            "unit": "1 กระปุก 290 บาท",
            "highlights": ["บำรุงข้อต่อ", "เพิ่มน้ำในกระดูก", "บำรุงข้อเข่า"],
            "voice_script": "จบปัญหาเข่าดังก๊อบแก๊บ",
        }

        response = client.post("/api/v1/knowledge/products/preview", json=[product])
        preview = response.json()

        self.assertEqual(response.status_code, 200)
        self.assertFalse(preview["persisted"])
        self.assertEqual(preview["products"][0]["id"], "PROD-001")
        self.assertFalse(preview["products"][0]["verified"])
        self.assertEqual(
            preview["products"][0]["excluded_unverified_fields"],
            ["category", "highlights", "price_regular", "unit", "voice_script"],
        )
        self.assertEqual(get_knowledge_base_status()["products"], 1)

    def test_promotion_import_preview_does_not_activate_unverified_promotion(self) -> None:
        client = TestClient(app)
        promotion = {
            "promo_id": "PROMO-BUY2GET1",
            "title": "ซื้อ 2 แถม 1",
            "applicable_products": ["PROD-001"],
            "price_special": 780,
            "details": "ซื้อกาแฟ 2 กล่อง แถมฟรีอีก 1 กล่อง ทันที",
            "free_shipping": True,
            "status": "active",
        }

        response = client.post("/api/v1/knowledge/promotions/preview", json=[promotion])
        preview = response.json()

        self.assertEqual(response.status_code, 200)
        self.assertFalse(preview["persisted"])
        self.assertEqual(preview["promotions"][0]["promo_id"], "PROMO-BUY2GET1")
        self.assertFalse(preview["promotions"][0]["verified"])
        self.assertEqual(
            preview["promotions"][0]["excluded_unverified_fields"],
            [
                "applicable_products",
                "details",
                "free_shipping",
                "price_special",
                "status",
            ],
        )
        self.assertEqual(get_knowledge_base_status()["active_promotions"], 0)


if __name__ == "__main__":
    unittest.main()
