import asyncio
import unittest
from unittest.mock import AsyncMock, patch

from app.services.firebase import image_import
from app.services.firebase.image_import import ImageLinkError

PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 32
FIREBASE_URL = "https://firebasestorage.googleapis.com/v0/b/demo.appspot.com/o/p%2Fa.png?alt=media&token=t"


class ImageImportTests(unittest.TestCase):
    def test_rejects_non_firebase_and_unsafe_links(self) -> None:
        for url in (
            "http://firebasestorage.googleapis.com/v0/b/x/o/a.png",
            "https://example.com/a.png",
            "https://127.0.0.1/a.png",
            "https://firebasestorage.googleapis.com.evil.com/a.png",
            "https://user:pw@firebasestorage.googleapis.com/a.png",
            "https://firebasestorage.googleapis.com:8443/a.png",
            "",
        ):
            with self.subTest(url=url), self.assertRaises(ImageLinkError):
                image_import.validate_source_url(url)

    def test_accepts_firebase_hosts(self) -> None:
        for url in (
            FIREBASE_URL,
            "https://storage.googleapis.com/bucket/a.png",
            "https://demo.firebasestorage.app/a.png",
        ):
            self.assertEqual(image_import.validate_source_url(url), url)

    def test_detects_type_from_content(self) -> None:
        self.assertEqual(image_import._detect_content_type(PNG), "image/png")
        with self.assertRaises(ImageLinkError):
            image_import._detect_content_type(b"<html>not an image</html>")

    def test_same_link_is_stored_once(self) -> None:
        saved = {"asset_id": "a" * 32, "filename": "a.png", "url": "/x", "content_type": "image/png", "size_bytes": 1}
        with (
            patch.object(image_import, "_existing_asset", side_effect=[None, saved]),
            patch.object(image_import, "_download", AsyncMock(return_value=PNG)) as download,
            patch.object(image_import, "upload_catalog_image", return_value=saved) as upload,
        ):
            first = asyncio.run(image_import.import_catalog_image(FIREBASE_URL, "admin@example.com"))
            second = asyncio.run(image_import.import_catalog_image(FIREBASE_URL, "admin@example.com"))
        self.assertFalse(first["reused"])
        self.assertTrue(second["reused"])
        self.assertEqual(download.await_count, 1)
        self.assertEqual(upload.call_count, 1)
        self.assertEqual(upload.call_args.kwargs["asset_id"], image_import._asset_id_for(FIREBASE_URL))
        self.assertEqual(upload.call_args.kwargs["source_url"], FIREBASE_URL)


if __name__ == "__main__":
    unittest.main()
