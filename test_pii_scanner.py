"""Tests for pii_scanner. All personal-data-like values are synthetic."""
import tempfile
import unittest
from pathlib import Path

import pii_scanner as ps


def make_iban(country: str, bban: str) -> str:
    """Build a valid IBAN from a country code and BBAN (computes check digits)."""
    numeric = "".join(str(int(c, 36)) for c in bban + country + "00")
    check = 98 - int(numeric) % 97
    return f"{country}{check:02d}{bban}"


class ValidatorTests(unittest.TestCase):
    def test_luhn_accepts_known_test_card(self):
        self.assertTrue(ps.luhn_valid("4111111111111111"))
        self.assertFalse(ps.luhn_valid("4111111111111112"))

    def test_generated_ibans_are_valid(self):
        self.assertTrue(ps.iban_valid(make_iban("IE", "AIBK93112345678912")))
        self.assertTrue(ps.iban_valid(make_iban("GB", "WEST12345698765432")))

    def test_iban_with_wrong_check_digits_is_rejected(self):
        good = make_iban("IE", "AIBK93112345678912")
        bad = good[:2] + ("00" if good[2:4] != "00" else "11") + good[4:]
        self.assertFalse(ps.iban_valid(bad))


class DetectionTests(unittest.TestCase):
    def kinds(self, line: str) -> list[str]:
        return [kind for _, _, kind in ps.find_spans(line)]

    def test_email_and_card(self):
        line = "user=jane.doe@example.test card=4111 1111 1111 1111"
        self.assertEqual(self.kinds(line), ["email address", "card number"])

    def test_card_failing_luhn_is_not_reported(self):
        self.assertEqual(self.kinds("card=4111 1111 1111 1112"), [])

    def test_ppsn_detected_by_format(self):
        self.assertEqual(self.kinds("ppsn=1234567T"), ["PPSN"])
        self.assertEqual(self.kinds("ppsn=7654321WA"), ["PPSN"])

    def test_plain_digits_are_not_ppsn(self):
        self.assertEqual(self.kinds("ref 12345678"), [])

    def test_iban_detected_and_not_split_into_other_kinds(self):
        line = f"iban={make_iban('IE', 'AIBK93112345678912')}"
        self.assertEqual(self.kinds(line), ["IBAN"])

    def test_international_phone(self):
        self.assertEqual(self.kinds("dial +353 85 555 0123"), ["phone number"])

    def test_national_phone(self):
        self.assertEqual(self.kinds("call 087 555 0199 now"), ["phone number"])

    def test_compact_national_number_not_flagged(self):
        self.assertEqual(self.kinds("batch=0510060436"), [])

    def test_ids_and_timestamps_are_not_flagged(self):
        line = "order=1234567890 ts=2026-10-14T12:00:01"
        self.assertEqual(self.kinds(line), [])


class FileTests(unittest.TestCase):
    def test_redaction_removes_value_and_keeps_line_count(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "app.log"
            src.write_text("pay 4111 1111 1111 1111 ok\nnothing here\n", encoding="utf-8")
            out = Path(tmp) / "clean"
            findings = ps.process_file(src, out)
            self.assertEqual(len(findings), 1)
            self.assertEqual(findings[0].line_no, 1)
            cleaned = (out / "app.log").read_text(encoding="utf-8")
            self.assertIn("[REDACTED:CARD_NUMBER]", cleaned)
            self.assertNotIn("4111", cleaned)
            self.assertEqual(cleaned.count("\n"), 2)

    def test_sample_log_covers_every_kind(self):
        sample = Path(__file__).parent / "samples" / "app.log"
        kinds = {f.kind for f in ps.process_file(sample)}
        self.assertEqual(
            kinds,
            {"IBAN", "card number", "email address", "PPSN", "phone number"},
        )


if __name__ == "__main__":
    unittest.main()
