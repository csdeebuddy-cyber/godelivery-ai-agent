import unittest

from fastapi.testclient import TestClient

from app.main import app
from app.api.v1.endpoints.live import _live_config
from app.services.knowledge_base import (
    get_knowledge_base_context,
    get_knowledge_base_status,
    search_knowledge_base,
)


class KnowledgeBaseTests(unittest.TestCase):
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
