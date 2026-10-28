import asyncio
import unittest
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from app.main import app
from app.api import admin as admin_api
from app.api.admin import _session_signer
from app.config import settings
from app.api.v1.endpoints.live import _live_config
from app.api.v1.endpoints import site as site_api, widget as widget_api
from app.schemas.admin import GoogleSheetsSettings
from app.schemas.site_content import SiteContent
from app.services.knowledge_base import (
    get_knowledge_base_context,
    get_knowledge_base_status,
    search_knowledge_base,
)
from app.services.google_sheets_knowledge import preview_google_sheets_knowledge


class KnowledgeBaseTests(unittest.TestCase):
    def test_google_sheets_knowledge_preview_reads_public_tabs_from_one_spreadsheet(self) -> None:
        configuration = {
            "spreadsheet_id": "shared-sheet-id",
            "range": "product!A2:E",
            "product_columns": {
                "product_id": 1,
                "product_name": 2,
                "regular_price": 3,
                "selling_price": 4,
                "stock_quantity": 5,
            },
            "promotion_range": "promotion!A2:C",
            "promotion_columns": {
                "promotion_id": 1,
                "promotion_name": 2,
                "conditions": 3,
            },
            "orders_range": "orders!A:O",
            "member_range": "MEMBER!A:F",
        }
        with (
            patch(
                "app.services.google_sheets_knowledge._access_token",
                return_value="token",
            ),
            patch(
                "app.services.google_sheets_knowledge._read_values",
                new=AsyncMock(
                    side_effect=[
                        [["SKU-1", "Product", "100", "80", "5"]],
                        [["PROMO-1", "Special", "Buy two, save 20%"]],
                    ]
                ),
            ) as read_values,
        ):
            result = asyncio.run(preview_google_sheets_knowledge(configuration))

        self.assertEqual(result["spreadsheet_id"], "shared-sheet-id")
        self.assertEqual(result["products"][0]["id"], "SKU-1")
        self.assertEqual(result["products"][0]["price_sale"], 80)
        self.assertEqual(result["promotions"][0]["promo_id"], "PROMO-1")
        self.assertEqual(result["promotions"][0]["details"], "Buy two, save 20%")
        self.assertFalse(result["persisted"])
        self.assertFalse(result["private_tabs"]["read"])
        self.assertEqual(read_values.call_count, 2)
        self.assertEqual(
            [call.kwargs["spreadsheet_id"] for call in read_values.call_args_list],
            ["shared-sheet-id", "shared-sheet-id"],
        )
        self.assertEqual(
            [call.kwargs["range_name"] for call in read_values.call_args_list],
            ["product!A2:E", "promotion!A2:C"],
        )

    def test_admin_sheets_preview_is_protected_and_reads_saved_configuration(self) -> None:
        client = TestClient(app)
        test_secret = "test-admin-session-secret-at-least-32-characters"
        preview = {
            "spreadsheet_id": "shared-sheet-id",
            "products_range": "product!A2:E",
            "promotions_range": "promotion!A2:C",
            "products": [{"id": "SKU-1", "name": "Product"}],
            "promotions": [{"promo_id": "PROMO-1", "title": "Deal"}],
            "private_tabs": {
                "orders_range": "orders!A2:Z",
                "member_range": "MEMBER!A2:Z",
                "read": False,
            },
            "persisted": False,
        }
        with patch.object(settings, "ADMIN_SESSION_SECRET", test_secret):
            unauthorized = client.get("/api/v1/admin/settings/google-sheets/preview")
            client.cookies.set(
                "godelivery_admin_session",
                _session_signer().dumps(
                    {"email": "smpmfast@gmail.com", "csrf_token": "csrf-allowed"}
                ),
            )
            with (
                patch.object(
                    admin_api,
                    "get_google_sheets_settings",
                    return_value={"configured": True, "spreadsheet_id": "shared-sheet-id"},
                ),
                patch.object(
                    admin_api,
                    "preview_google_sheets_knowledge",
                    new=AsyncMock(return_value=preview),
                ) as read_preview,
            ):
                response = client.get("/api/v1/admin/settings/google-sheets/preview")

        self.assertEqual(unauthorized.status_code, 401)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), preview)
        read_preview.assert_awaited_once()

    def test_widget_site_creation_requires_admin_and_generates_install_snippet(self) -> None:
        client = TestClient(app)
        test_secret = "test-admin-session-secret-at-least-32-characters"
        payload = {
            "name": "Campaign landing page",
            "allowed_domains": ["www.example.com", "example.com"],
            "title": "GoDelivery",
            "assistant_name": "ผู้ช่วย",
            "launch_text": "ถามเรื่องโปรโมชั่น",
            "placeholder": "พิมพ์คำถาม",
            "primary_color": "#ff6600",
            "speech_language": "th-TH",
            "voice": "all-day",
        }

        with patch.object(settings, "ADMIN_SESSION_SECRET", test_secret):
            unauthorized = client.post("/api/v1/admin/widget-sites", json=payload)
            client.cookies.set(
                "godelivery_admin_session",
                _session_signer().dumps(
                    {"email": "smpmfast@gmail.com", "csrf_token": "csrf-allowed"}
                ),
            )
            invalid_csrf = client.post("/api/v1/admin/widget-sites", json=payload)
            with patch.object(
                admin_api,
                "save_widget_site",
                side_effect=lambda *, site_id, configuration, created_by: {
                    "site_id": site_id,
                    **configuration,
                },
            ):
                created = client.post(
                    "/api/v1/admin/widget-sites",
                    json=payload,
                    headers={"X-CSRF-Token": "csrf-allowed"},
                )

        self.assertEqual(unauthorized.status_code, 401)
        self.assertEqual(invalid_csrf.status_code, 403)
        self.assertEqual(created.status_code, 200)
        self.assertIn('"siteId":"', created.json()["embed_code"])
        self.assertIn("http://testserver/static/widget.js", created.json()["embed_code"])
        self.assertEqual(created.json()["allowed_domains"], ["www.example.com", "example.com"])

    def test_widget_site_rejects_url_paths_in_allowed_domain(self) -> None:
        client = TestClient(app)
        test_secret = "test-admin-session-secret-at-least-32-characters"
        payload = {
            "name": "Campaign",
            "allowed_domains": ["https://example.com/landing"],
        }
        with patch.object(settings, "ADMIN_SESSION_SECRET", test_secret):
            client.cookies.set(
                "godelivery_admin_session",
                _session_signer().dumps(
                    {"email": "smpmfast@gmail.com", "csrf_token": "csrf-allowed"}
                ),
            )
            response = client.post(
                "/api/v1/admin/widget-sites",
                json=payload,
                headers={"X-CSRF-Token": "csrf-allowed"},
            )

        self.assertEqual(response.status_code, 422)

    def test_widget_chat_accepts_allowed_domain_and_rejects_other_origins(self) -> None:
        client = TestClient(app)
        site = {"site_id": "site-test", "allowed_domains": ["ads.example.com"]}
        with (
            patch.object(widget_api, "get_widget_site", return_value=site),
            patch.object(widget_api, "AIService") as service_class,
        ):
            service_class.return_value.generate_response = AsyncMock(
                return_value="คำตอบจากระบบกลาง"
            )
            preflight = client.options(
                "/api/v1/widget/chat",
                params={"site_id": "site-test"},
                headers={
                    "Origin": "https://ads.example.com",
                    "Access-Control-Request-Method": "POST",
                    "Access-Control-Request-Headers": "content-type",
                },
            )
            allowed = client.post(
                "/api/v1/widget/chat",
                params={"site_id": "site-test"},
                headers={"Origin": "https://ads.example.com"},
                json={"message": "มีโปรโมชั่นอะไรบ้าง"},
            )
            blocked = client.post(
                "/api/v1/widget/chat",
                params={"site_id": "site-test"},
                headers={"Origin": "https://attacker.example"},
                json={"message": "hello"},
            )

        self.assertEqual(preflight.status_code, 204)
        self.assertEqual(
            preflight.headers["access-control-allow-origin"],
            "https://ads.example.com",
        )
        self.assertEqual(allowed.status_code, 200)
        self.assertEqual(allowed.json()["reply"], "คำตอบจากระบบกลาง")
        self.assertEqual(
            allowed.headers["access-control-allow-origin"],
            "https://ads.example.com",
        )
        self.assertEqual(blocked.status_code, 403)

    def test_customer_and_admin_routes_are_available(self) -> None:
        client = TestClient(app)

        root_response = client.get("/", follow_redirects=False)
        product_response = client.get("/product")
        chat_response = client.get("/chatandshop")
        home_styles_response = client.get("/static/home.css")
        home_script_response = client.get("/static/home.js")
        product_styles_response = client.get("/static/product.css")
        product_script_response = client.get("/static/product.js")
        login_response = client.get("/dashboard/admin/login")
        admin_response = client.get("/dashboard/admin", follow_redirects=False)
        api_response = client.get("/api/v1/admin/status")
        robots_response = client.get("/robots.txt")

        self.assertEqual(root_response.status_code, 200)
        self.assertIn("GoDelivery | 711shopping", root_response.text)
        self.assertIn('href="/chatandshop"', root_response.text)
        self.assertIn('href="/product"', root_response.text)
        self.assertIn("สินค้าแนะนำ", root_response.text)
        self.assertIn("noindex", root_response.headers["x-robots-tag"])
        self.assertEqual(product_response.status_code, 200)
        self.assertIn("สินค้าทั้งหมด", product_response.text)
        self.assertIn('id="product-search"', product_response.text)
        self.assertIn('href="/product"', product_response.text)
        self.assertEqual(chat_response.status_code, 200)
        self.assertIn("/dashboard/admin", chat_response.text)
        self.assertIn('name="googlebot" content="noindex', chat_response.text)
        self.assertEqual(home_styles_response.status_code, 200)
        self.assertIn(".hero-card", home_styles_response.text)
        self.assertEqual(home_script_response.status_code, 200)
        self.assertIn("/api/v1/site/orders", home_script_response.text)
        self.assertEqual(product_styles_response.status_code, 200)
        self.assertIn(".store-product-card", product_styles_response.text)
        self.assertEqual(product_script_response.status_code, 200)
        self.assertIn("/api/v1/site/content", product_script_response.text)
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

    def test_public_site_content_is_read_only_and_returns_only_published_content(self) -> None:
        content = SiteContent(
            company={"title": "About", "body": "Public text"},
            products=[
                {
                    "product_id": "P-1",
                    "name": "Soap",
                    "description": "Product description",
                    "image_id": "0123456789abcdef0123456789abcdef",
                    "regular_price": 25,
                    "sale_price": 20,
                    "stock_quantity": 4,
                    "active": True,
                },
                {
                    "product_id": "P-2",
                    "name": "Hidden product",
                    "description": "",
                    "regular_price": 99,
                    "sale_price": None,
                    "stock_quantity": 2,
                    "active": False,
                },
            ],
            promotions=[
                {
                    "promotion_id": "PROMO-1",
                    "title": "Live",
                    "details": "Details",
                    "active": True,
                },
                {
                    "promotion_id": "PROMO-2",
                    "title": "Hidden",
                    "details": "Not public",
                    "active": False,
                },
            ],
        ).model_dump()
        with patch.object(site_api, "get_site_content", return_value=content):
            response = TestClient(app).get("/api/v1/site/content")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["company"]["body"], "Public text")
        self.assertEqual(
            [product["product_id"] for product in response.json()["products"]],
            ["P-1"],
        )
        self.assertEqual(
            response.json()["products"][0]["image_url"],
            "/api/v1/site/assets/0123456789abcdef0123456789abcdef",
        )
        self.assertEqual(
            [promotion["promotion_id"] for promotion in response.json()["promotions"]],
            ["PROMO-1"],
        )
        self.assertEqual(response.headers["cache-control"], "no-store")
        self.assertNotIn("updated_by", response.json())

    def test_admin_site_content_requires_authentication_and_csrf_then_saves(self) -> None:
        client = TestClient(app)
        content = {
            "company": {"title": "เกี่ยวกับบริษัท", "body": "ข้อมูลบริษัท"},
            "terms": {"title": "ข้อกำหนด", "body": ""},
            "security": {"title": "Privacy Policy", "body": "แจ้งการใช้ข้อมูล"},
            "shipping": {"title": "การจัดส่ง", "body": ""},
            "returns": {"title": "การคืนสินค้า", "body": ""},
            "faqs": [{"question": "สอบถาม", "answer": "ติดต่อเรา"}],
            "products": [],
            "promotions": [],
        }
        test_secret = "test-admin-session-secret-at-least-32-characters"
        with patch.object(settings, "ADMIN_SESSION_SECRET", test_secret):
            unauthorized = client.get("/api/v1/admin/settings/site-content")
            client.cookies.set(
                "godelivery_admin_session",
                _session_signer().dumps(
                    {"email": "smpmfast@gmail.com", "csrf_token": "site-csrf"}
                ),
            )
            with (
                patch.object(admin_api, "get_site_content", return_value=content),
                patch.object(admin_api, "save_site_content", return_value=content) as save,
            ):
                loaded = client.get("/api/v1/admin/settings/site-content")
                missing_csrf = client.put(
                    "/api/v1/admin/settings/site-content",
                    json=content,
                )
                saved = client.put(
                    "/api/v1/admin/settings/site-content",
                    headers={"X-CSRF-Token": "site-csrf"},
                    json=content,
                )

        self.assertEqual(unauthorized.status_code, 401)
        self.assertEqual(loaded.status_code, 200)
        self.assertEqual(missing_csrf.status_code, 403)
        self.assertEqual(saved.status_code, 200)
        self.assertEqual(saved.json()["status"], "saved")
        self.assertEqual(save.call_args.kwargs["updated_by"], "smpmfast@gmail.com")

    def test_site_content_rejects_duplicate_product_ids_and_invalid_sale_price(self) -> None:
        product = {
            "product_id": "P-1",
            "name": "Soap",
            "description": "",
            "regular_price": 10,
            "sale_price": 12,
            "stock_quantity": 2,
            "active": True,
        }
        with self.assertRaises(ValueError):
            SiteContent(products=[product])

        product["sale_price"] = 8
        with self.assertRaises(ValueError):
            SiteContent(products=[product, product])

    def test_customer_order_checks_consent_and_appends_exact_orders_columns(self) -> None:
        client = TestClient(app)
        test_secret = "test-admin-session-secret-at-least-32-characters"
        content = SiteContent(
            products=[
                {
                    "product_id": "P-1",
                    "name": "Soap",
                    "description": "",
                    "regular_price": 25,
                    "sale_price": 20,
                    "stock_quantity": 5,
                    "active": True,
                }
            ],
            security={"title": "Privacy Policy", "body": "Customer data policy"},
        ).model_dump()
        payload = {
            "customer": "Test Customer",
            "address": "123 Main Street",
            "address1": "District",
            "postcode": "10110",
            "phone_number": "0812345678",
            "items": [
                {"product_id": "P-1", "quantity": 1},
                {"product_id": "P-1", "quantity": 2},
            ],
            "remark": "Call first",
            "privacy_consent": True,
        }
        with (
            patch.object(settings, "ADMIN_SESSION_SECRET", test_secret),
            patch.object(site_api, "get_site_content", return_value=content),
            patch.object(
                site_api,
                "_configured_sheet_settings",
                return_value={
                    "configured": True,
                    "spreadsheet_id": "shared-sheet-id",
                    "orders_range": "orders!A:O",
                    "member_range": "MEMBER!A:F",
                },
            ),
            patch.object(
                site_api,
                "append_customer_row",
                new=AsyncMock(return_value={"updated_range": "orders!A2:O2"}),
            ) as append_row,
        ):
            no_consent = client.post(
                "/api/v1/site/orders",
                json={**payload, "privacy_consent": False},
            )
            tampered_price = client.post(
                "/api/v1/site/orders",
                json={**payload, "items": [{"product_id": "P-1", "quantity": 3, "price": 0}]},
            )
            response = client.post("/api/v1/site/orders", json=payload)

        self.assertEqual(no_consent.status_code, 422)
        self.assertEqual(tampered_price.status_code, 422)
        self.assertEqual(response.status_code, 201)
        self.assertTrue(response.json()["ordernumber"].startswith("GD"))
        append_row.assert_awaited_once()
        self.assertEqual(append_row.await_args.kwargs["range_name"], "orders!A:O")
        values = append_row.await_args.kwargs["values"]
        self.assertEqual(len(values), 15)
        self.assertEqual(values[2:10], [
            "เว็บไซต์",
            "Test Customer",
            "123 Main Street",
            "District",
            "10110",
            "0812345678",
            "Soap x 3",
            60,
        ])
        self.assertIn("Call first", values[10])
        self.assertIn("Privacy Policy", values[10])
        self.assertEqual(values[11:15], ["เก็บเงินปลายทาง", 60, "", "รอยืนยันจากเจ้าหน้าที่"])

    def test_member_registration_requires_privacy_consent_and_writes_minimal_columns(self) -> None:
        client = TestClient(app)
        payload = {
            "customer": "Test Member",
            "phone_number": "0812345678",
            "email": "member@example.com",
            "privacy_consent": True,
        }
        with (
            patch.object(site_api, "get_site_content", return_value={
                "security": {"title": "Privacy Policy", "body": "Customer data policy"},
                "products": [],
                "promotions": [],
                "faqs": [],
                "company": {"title": "", "body": ""},
                "terms": {"title": "", "body": ""},
                "shipping": {"title": "", "body": ""},
                "returns": {"title": "", "body": ""},
            }),
            patch.object(
                site_api,
                "_configured_sheet_settings",
                return_value={
                    "configured": True,
                    "spreadsheet_id": "shared-sheet-id",
                    "member_range": "MEMBER!A:F",
                },
            ),
            patch.object(
                site_api,
                "append_customer_row",
                new=AsyncMock(return_value={"updated_range": "MEMBER!A2:F2"}),
            ) as append_row,
        ):
            rejected = client.post(
                "/api/v1/site/members",
                json={**payload, "privacy_consent": False},
            )
            response = client.post("/api/v1/site/members", json=payload)

        self.assertEqual(rejected.status_code, 422)
        self.assertEqual(response.status_code, 201)
        values = append_row.await_args.kwargs["values"]
        self.assertEqual(len(values), 6)
        self.assertEqual(values[2:5], ["Test Member", "0812345678", "member@example.com"])
        self.assertIn("Privacy Policy", values[5])

    def test_admin_session_requires_allowed_email_and_disables_unconfigured_storage(self) -> None:
        client = TestClient(app)
        test_secret = "test-admin-session-secret-at-least-32-characters"

        with (
            patch.object(settings, "ADMIN_SESSION_SECRET", test_secret),
            patch.object(settings, "FIRESTORE_PROJECT_ID", None),
        ):
            allowed_cookie = _session_signer().dumps(
                {"email": "smpmfast@gmail.com", "csrf_token": "test-csrf-token"}
            )
            client.cookies.set("godelivery_admin_session", allowed_cookie)
            overview_response = client.get("/api/v1/admin/overview")
            self.assertEqual(overview_response.status_code, 200)
            self.assertEqual(overview_response.json()["admin_email"], "smpmfast@gmail.com")
            self.assertFalse(overview_response.json()["storage"]["editing_enabled"])

            other_user_cookie = _session_signer().dumps(
                {"email": "other@example.com", "csrf_token": "test-csrf-token"}
            )
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
            patch.object(settings, "FIRESTORE_PROJECT_ID", None),
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

    def test_sheets_settings_are_admin_only_csrf_protected_and_saved_to_firestore(self) -> None:
        client = TestClient(app)
        test_secret = "test-admin-session-secret-at-least-32-characters"
        payload = {
            "spreadsheet_id": "1Abcdefghijklmnopqrstuvwxyz0123456789",
            "range": "product!A2:E",
            "product_columns": {
                "product_id": 1,
                "product_name": 2,
                "regular_price": 3,
                "selling_price": 4,
                "stock_quantity": 5,
            },
            "promotion_range": "promotion!A2:C",
            "promotion_columns": {
                "promotion_id": 1,
                "promotion_name": 2,
                "conditions": 3,
            },
        }

        with patch.object(settings, "ADMIN_SESSION_SECRET", test_secret):
            signed_cookie = _session_signer().dumps(
                {"email": "smpmfast@gmail.com", "csrf_token": "csrf-allowed"}
            )
            client.cookies.clear()
            unauthorized = client.put(
                "/api/v1/admin/settings/google-sheets",
                json=payload,
                headers={"X-CSRF-Token": "csrf-allowed"},
            )
            client.cookies.set("godelivery_admin_session", signed_cookie)
            invalid_csrf = client.put(
                "/api/v1/admin/settings/google-sheets",
                json=payload,
                headers={"X-CSRF-Token": "wrong-token"},
            )
            with patch.object(
                admin_api,
                "save_google_sheets_settings",
                return_value={
                    "configured": True,
                    "spreadsheet_id": payload["spreadsheet_id"],
                    "range": payload["range"],
                    "product_columns": payload["product_columns"],
                    "promotion_range": payload["promotion_range"],
                    "promotion_columns": payload["promotion_columns"],
                    "orders_range": "orders!A2:Z",
                    "member_range": "MEMBER!A2:Z",
                },
            ) as save_settings:
                saved = client.put(
                    "/api/v1/admin/settings/google-sheets",
                    json=payload,
                    headers={"X-CSRF-Token": "csrf-allowed"},
                )

        self.assertEqual(unauthorized.status_code, 401)
        self.assertEqual(invalid_csrf.status_code, 403)
        self.assertEqual(saved.status_code, 200)
        self.assertEqual(saved.json()["status"], "saved")
        self.assertIn("preview action", saved.json()["message"])
        save_settings.assert_called_once_with(
            spreadsheet_id=payload["spreadsheet_id"],
            range_name=payload["range"],
            product_columns=payload["product_columns"],
            promotion_range=payload["promotion_range"],
            promotion_columns=payload["promotion_columns"],
            orders_range="orders!A:O",
            member_range="MEMBER!A:F",
            updated_by="smpmfast@gmail.com",
        )

    def test_sheets_settings_validate_unique_column_mapping_and_support_defaults(self) -> None:
        client = TestClient(app)
        test_secret = "test-admin-session-secret-at-least-32-characters"
        payload = {
            "spreadsheet_id": "1Abcdefghijklmnopqrstuvwxyz0123456789",
            "range": "product!A2:E",
            "promotion_range": "promotion!A2:C",
            "product_columns": {
                "product_id": 1,
                "product_name": 2,
                "regular_price": 3,
                "selling_price": 4,
                "stock_quantity": 4,
            },
            "promotion_columns": {
                "promotion_id": 1,
                "promotion_name": 2,
                "conditions": 2,
            },
        }

        with patch.object(settings, "ADMIN_SESSION_SECRET", test_secret):
            client.cookies.set(
                "godelivery_admin_session",
                _session_signer().dumps(
                    {"email": "smpmfast@gmail.com", "csrf_token": "csrf-allowed"}
                ),
            )
            duplicate_column = client.put(
                "/api/v1/admin/settings/google-sheets",
                json=payload,
                headers={"X-CSRF-Token": "csrf-allowed"},
            )

        self.assertEqual(duplicate_column.status_code, 422)
        payload["product_columns"]["stock_quantity"] = 5
        promotion_duplicate_column = client.put(
            "/api/v1/admin/settings/google-sheets",
            json=payload,
            headers={"X-CSRF-Token": "csrf-allowed"},
        )
        self.assertEqual(promotion_duplicate_column.status_code, 422)
        self.assertEqual(
            GoogleSheetsSettings.model_validate(
                {
                    "spreadsheet_id": "1Abcdefghijklmnopqrstuvwxyz0123456789",
                    "range": "product!A2:E",
                }
            ).product_columns.model_dump(),
            {
                "product_id": 1,
                "product_name": 2,
                "regular_price": 3,
                "selling_price": 4,
                "stock_quantity": 5,
            },
        )
        self.assertEqual(
            GoogleSheetsSettings.model_validate(
                {
                    "spreadsheet_id": "1Abcdefghijklmnopqrstuvwxyz0123456789",
                    "range": "product!A2:E",
                }
            ).promotion_range,
            "promotion!A2:C",
        )
        self.assertEqual(
            GoogleSheetsSettings.model_validate(
                {
                    "spreadsheet_id": "1Abcdefghijklmnopqrstuvwxyz0123456789",
                    "range": "product!A2:E",
                }
            ).promotion_columns.model_dump(),
            {"promotion_id": 1, "promotion_name": 2, "conditions": 3},
        )
        defaults = GoogleSheetsSettings.model_validate(
            {
                "spreadsheet_id": "1Abcdefghijklmnopqrstuvwxyz0123456789",
                "range": "product!A2:E",
            }
        )
        self.assertEqual(defaults.orders_range, "orders!A:O")
        self.assertEqual(defaults.member_range, "MEMBER!A:F")

    def test_sheets_settings_validate_input_and_return_unavailable_if_firestore_missing(self) -> None:
        client = TestClient(app)
        test_secret = "test-admin-session-secret-at-least-32-characters"

        with (
            patch.object(settings, "ADMIN_SESSION_SECRET", test_secret),
            patch.object(settings, "FIRESTORE_PROJECT_ID", None),
        ):
            signed_cookie = _session_signer().dumps(
                {"email": "smpmfast@gmail.com", "csrf_token": "csrf-allowed"}
            )
            client.cookies.set("godelivery_admin_session", signed_cookie)
            invalid_payload = client.put(
                "/api/v1/admin/settings/google-sheets",
                json={"spreadsheet_id": "x", "range": "Products!A2:E"},
                headers={"X-CSRF-Token": "csrf-allowed"},
            )
            unavailable = client.get("/api/v1/admin/settings/google-sheets")

        self.assertEqual(invalid_payload.status_code, 422)
        self.assertEqual(unavailable.status_code, 503)
        self.assertEqual(unavailable.json()["detail"]["code"], "firestore_unavailable")

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

    def test_product_preview_accepts_sheet_price_and_stock_fields_but_does_not_publish_them(self) -> None:
        client = TestClient(app)
        response = client.post(
            "/api/v1/knowledge/products/preview",
            json=[
                {
                    "id": "SHEET-001",
                    "name": "ตัวอย่างสินค้า",
                    "price_regular": 500,
                    "price_sale": 450,
                    "stock_quantity": 12,
                }
            ],
        )

        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.json()["persisted"])
        self.assertEqual(
            response.json()["products"][0]["excluded_unverified_fields"],
            ["price_regular", "price_sale", "stock_quantity"],
        )

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
