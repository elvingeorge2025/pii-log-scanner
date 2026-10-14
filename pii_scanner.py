#!/usr/bin/env python3
"""pii_scanner: find personal data in application log files without printing it.

Detects email addresses, phone numbers, IBANs (mod-97 check), payment card
numbers (Luhn check) and Irish PPS numbers (format check only).

Usage:
    python pii_scanner.py app.log other.log
    python pii_scanner.py app.log --redact-dir clean/

Exit status: 0 = nothing found, 1 = personal data found, 2 = usage error.
"""
from __future__ import annotations

import argparse
import re
import sys
from collections import Counter
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Finding:
    """One detected value. The value itself is never stored or printed."""

    file: str
    line_no: int
    kind: str


# ---------- validators ----------

def luhn_valid(digits: str) -> bool:
    total = 0
    for i, ch in enumerate(reversed(digits)):
        d = int(ch)
        if i % 2 == 1:
            d *= 2
            if d > 9:
                d -= 9
        total += d
    return total % 10 == 0


def iban_valid(value: str) -> bool:
    """ISO 13616 mod-97 check. Length and character rules are checked loosely."""
    s = value.replace(" ", "").upper()
    if not re.fullmatch(r"[A-Z]{2}\d{2}[A-Z0-9]{11,30}", s):
        return False
    rearranged = s[4:] + s[:4]
    numeric = "".join(str(int(c, 36)) for c in rearranged)  # A=10 ... Z=35
    return int(numeric) % 97 == 1


def card_valid(value: str) -> bool:
    digits = re.sub(r"[ -]", "", value)
    return 13 <= len(digits) <= 19 and luhn_valid(digits)


def phone_valid(value: str) -> bool:
    digits = re.sub(r"\D", "", value)
    if not 9 <= len(digits) <= 15:
        return False
    if value.startswith("+"):
        return True  # international form, e.g. +353 85 555 0123
    # National form (087 555 0199) must use separators. A bare run of digits
    # starting with 0 is too often a batch or reference number.
    return value.startswith("0") and bool(re.search(r"[ \-()]", value))


# ---------- detectors ----------
# Order matters: earlier detectors claim their spans first, so a card number
# is not also reported as a phone number.

IBAN_RE = re.compile(r"\b[A-Z]{2}\d{2}(?: ?[A-Z0-9]{4}){2,7}(?: ?[A-Z0-9]{1,3})?\b")
CARD_RE = re.compile(r"(?<!\d)(?:\d[ -]?){12,18}\d(?!\d)")
EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}")
# Irish PPS number: 7 digits, one letter, optional second letter (format only).
PPSN_RE = re.compile(r"(?<![A-Za-z0-9])\d{7}[A-W][A-IW]?(?![A-Za-z0-9])")
PHONE_RE = re.compile(r"(?<![\w+])\+?\d[\d \-()]{6,18}\d(?!\w)")

DETECTORS = [
    ("IBAN", IBAN_RE, iban_valid),
    ("card number", CARD_RE, card_valid),
    ("email address", EMAIL_RE, lambda _: True),
    ("PPSN", PPSN_RE, lambda _: True),
    ("phone number", PHONE_RE, phone_valid),
]


def find_spans(line: str) -> list[tuple[int, int, str]]:
    """Return sorted (start, end, kind) for every validated match in one line."""
    accepted: list[tuple[int, int, str]] = []
    for kind, regex, check in DETECTORS:
        for m in regex.finditer(line):
            start, end = m.span()
            if any(start < a_end and a_start < end for a_start, a_end, _ in accepted):
                continue
            if check(m.group()):
                accepted.append((start, end, kind))
    return sorted(accepted)


# ---------- file processing ----------

def process_file(path: Path, redact_dir: Path | None = None) -> list[Finding]:
    """Scan one file. Optionally write a redacted copy into redact_dir."""
    findings: list[Finding] = []
    cleaned: list[str] = []
    with path.open(encoding="utf-8", errors="replace") as fh:
        for line_no, raw in enumerate(fh, start=1):
            body = raw.rstrip("\r\n")
            ending = raw[len(body):]
            spans = find_spans(body)
            findings.extend(Finding(str(path), line_no, kind) for _, _, kind in spans)
            # Replace from the end so earlier span indices stay valid.
            for start, end, kind in reversed(spans):
                label = f"[REDACTED:{kind.upper().replace(' ', '_')}]"
                body = body[:start] + label + body[end:]
            cleaned.append(body + ending)
    if redact_dir is not None:
        redact_dir.mkdir(parents=True, exist_ok=True)
        (redact_dir / path.name).write_text("".join(cleaned), encoding="utf-8")
    return findings


# ---------- CLI ----------

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Report personal data in log files without printing the values."
    )
    parser.add_argument("paths", nargs="+", type=Path, help="log files to scan")
    parser.add_argument("--redact-dir", type=Path, help="write redacted copies here")
    args = parser.parse_args(argv)

    all_findings: list[Finding] = []
    for path in args.paths:
        if not path.is_file():
            print(f"error: not a file: {path}", file=sys.stderr)
            return 2
        all_findings.extend(process_file(path, args.redact_dir))

    for f in all_findings:
        print(f"{f.file}: {f.kind} detected at line {f.line_no}, value masked")

    counts = Counter(f.kind for f in all_findings)
    print(f"\nScanned {len(args.paths)} file(s): {len(all_findings)} finding(s)")
    for kind, n in counts.most_common():
        print(f"  {kind}: {n}")
    return 1 if all_findings else 0


if __name__ == "__main__":
    sys.exit(main())
