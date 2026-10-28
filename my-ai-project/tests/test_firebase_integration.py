import unittest
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from app.api import admin as admin_api
from app.api.admin import _session_signer
from app.api.v1.endpoints import site as site_api
from app.config import settings
from app.main import app
from app.schemas.site_content import ProductItem
from app.services.firebase.security import validate_catalog_image
from app.services.firebase.storage import get_catalog_image


PNG_DATA = b"\x89PNG\r\n\x1a\n" + b"test"
ASSET_ID = "0123456789abcdef0123456789abcdef"


class FirebaseIntegrationTests(unittest.TestCase):
    def test_catalog_image_validation_checks_format_and_size(self) -> None:
        self.assertEqual(validate_catalog_image(PNG_DATA, "image/png"), ".png")
        with self.assertRaises(ValueError):
            validate_catalog_image(PNG_DATA, "image/jpeg")
        with self.assertRaises(ValueError):
            validate_catalog_image(b"", "image/png")
        with self.assertRaises(ValueError):
            validate_catalog_image(b"\x89PNG\r\n\x1a\n" + b"x" * (5 * 1024 * 1024), "image/png")

    def test_product_image_id_must_be_a_generated_asset_id(self) -> None:
        product = ProductItem(
            product_id="SKU-1",
            name="Sample",
            regular_price=1,
            image_id=ASSET_ID,
        )
        self.assertEqual(product.image_id, ASSET_ID)
        with self.assertRaises(ValueError):
            ProductItem(
                product_id="SKU-2",
                name="Invalid",
                regular_price=1,
                image_id="../private",
            )

    def test_private_asset_metadata_never_returns_an_image(self) -> None:
        document = MagicMock()
        document.get.return_value.exists = True
        document.get.return_value.to_dict.return_value = {
            "visibility": "private",
            "object_path": f"catalog/{ASSET_ID}.png",
            "content_type": "image/png",
        }
        with patch("app.services.firebase.storage._asset_document", return_value=document):
            image = get_catalog_image(ASSET_ID)

        self.assertIsNone(image)

    def test_public_image_endpoint_returns_only_valid_asset_ids(self) -> None:
        client = TestClient(app)
        with patch.object(site_api, "get_catalog_image", return_value=(PNG_DATA, "image/png")) as get_image:
            response = client.get(f"/api/v1/site/assets/{ASSET_ID}")
            invalid = client.get("/api/v1/site/assets/not-an-asset")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content, PNG_DATA)
        self.assertEqual(response.headers["content-type"], "image/png")
        self.assertEqual(response.headers["x-content-type-options"], "nosniff")
        self.assertIn("immutable", response.headers["cache-control"])
        self.assertEqual(invalid.status_code, 404)
        self.assertEqual(get_image.call_count, 1)

    def test_admin_image_upload_requires_session_and_csrf(self) -> None:
        client = TestClient(app)
        test_secret = "test-admin-session-secret-at-least-32-characters"
        image_file = ("sample.png", PNG_DATA, "image/png")
        with patch.object(settings, "ADMIN_SESSION_SECRET", test_secret):
            unauthorized = client.post(
                "/api/v1/admin/assets/images",
                files={"file": image_file},
            )
            client.cookies.set(
                "godelivery_admin_session",
                _session_signer().dumps(
                    {"email": "smpmfast@gmail.com", "csrf_token": "asset-csrf"}
                ),
            )
            with patch.object(
                admin_api,
                "upload_catalog_image",
                return_value={"asset_id": ASSET_ID, "filename": "sample.png"},
            ) as upload:
                missing_csrf = client.post(
                    "/api/v1/admin/assets/images",
                    files={"file": image_file},
                )
                uploaded = client.post(
                    "/api/v1/admin/assets/images",
                    headers={"X-CSRF-Token": "asset-csrf"},
                    files={"file": image_file},
                )

        self.assertEqual(unauthorized.status_code, 401)
        self.assertEqual(missing_csrf.status_code, 403)
        self.assertEqual(uploaded.status_code, 201)
        self.assertEqual(uploaded.json()["asset_id"], ASSET_ID)
        upload.assert_called_once_with(
            data=PNG_DATA,
            content_type="image/png",
            filename="sample.png",
            uploaded_by="smpmfast@gmail.com",
        )

    def test_admin_image_upload_rejects_mismatched_mime_type(self) -> None:
        client = TestClient(app)
        test_secret = "test-admin-session-secret-at-least-32-characters"
        with patch.object(settings, "ADMIN_SESSION_SECRET", test_secret):
            client.cookies.set(
                "godelivery_admin_session",
                _session_signer().dumps(
                    {"email": "smpmfast@gmail.com", "csrf_token": "asset-csrf"}
                ),
            )
            response = client.post(
                "/api/v1/admin/assets/images",
                headers={"X-CSRF-Token": "asset-csrf"},
                files={"file": ("sample.png", PNG_DATA, "image/jpeg")},
            )

        self.assertEqual(response.status_code, 422)


if __name__ == "__main__":
    unittest.main()
