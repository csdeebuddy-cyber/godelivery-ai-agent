import unittest

from app.services import address_book


class AddressBookTests(unittest.TestCase):
    def test_exact_match_with_prefixes_and_alias(self) -> None:
        result = address_book.verify_address("แขวงบางนาเหนือ", "เขตบางนา", "กทม", "10260")
        self.assertTrue(result["match"])
        self.assertEqual(result["address"]["province"], "กรุงเทพมหานคร")
        self.assertEqual(result["address"]["postcode"], "10260")

    def test_mismatch_returns_candidates_for_postcode(self) -> None:
        result = address_book.verify_address("บางนาเหนือ", "บางนา", "เชียงใหม่", "10260")
        self.assertFalse(result["match"])
        self.assertTrue(result["found"])
        self.assertEqual(result["areas"][0]["province"], "กรุงเทพมหานคร")

    def test_unknown_or_invalid_postcode(self) -> None:
        self.assertFalse(address_book.lookup_postcode("00000")["found"])
        self.assertFalse(address_book.lookup_postcode("12")["found"])
        self.assertFalse(address_book.verify_address("a", "b", "c", "abc")["match"])

    def test_dataset_is_loaded(self) -> None:
        self.assertGreater(len(address_book._rows()), 7000)


if __name__ == "__main__":
    unittest.main()
