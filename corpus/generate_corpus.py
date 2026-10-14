#!/usr/bin/env python3
"""Generate a labelled synthetic corpus for measuring the scanner.

Every value is generated here, and every label is written here, before the
scanner is ever run. Nothing is taken from real logs or real people.

Output: labelled_corpus.jsonl, one JSON object per line:
    {"line": "<log line>", "expected": ["<kind>", ...]}
An empty "expected" list means the line contains no personal data.
"""
import json
import random
import string
import uuid
from pathlib import Path

OUT = Path(__file__).resolve().parent / "labelled_corpus.jsonl"
rng = random.Random(42)  # fixed seed, so the corpus is reproducible


# ---------- helpers (independent of the scanner's own code) ----------

def digits(n):
    return "".join(rng.choices("0123456789", k=n))


def luhn_valid(s):
    total = 0
    for i, ch in enumerate(reversed(s)):
        d = int(ch)
        if i % 2 == 1:
            d *= 2
            if d > 9:
                d -= 9
        total += d
    return total % 10 == 0


def add_luhn_digit(partial):
    for c in "0123456789":
        if luhn_valid(partial + c):
            return partial + c


def make_iban(country, bban):
    numeric = "".join(str(int(c, 36)) for c in bban + country + "00")
    check = 98 - int(numeric) % 97
    return f"{country}{check:02d}{bban}"


def group(s, n=4):
    return " ".join(s[i:i + n] for i in range(0, len(s), n))


# ---------- positive generators: each returns a value that IS personal data ----------

def gen_email():
    user = "".join(rng.choices(string.ascii_lowercase, k=rng.randint(5, 10)))
    return f"{user}@example.{rng.choice(['test', 'org'])}"


def gen_card():
    card = add_luhn_digit("4" + digits(14))  # 16 digits, valid Luhn
    style = rng.choice(["plain", "spaced", "dashed"])
    if style == "spaced":
        return group(card)
    if style == "dashed":
        return f"{card[:4]}-{card[4:8]}-{card[8:12]}-{card[12:]}"
    return card


def gen_iban():
    country = rng.choice(["IE", "GB"])
    bban = "".join(rng.choices(string.ascii_uppercase, k=4)) + digits(14)
    iban = make_iban(country, bban)
    return group(iban) if rng.random() < 0.5 else iban


def gen_ppsn():
    s = digits(7) + rng.choice("ABCDEFGHIJKLMNOPQRSTUVW")
    if rng.random() < 0.3:
        s += rng.choice("ABCDEFGHIW")
    return s


def gen_phone():
    style = rng.choice(["national", "intl", "intl_compact"])
    if style == "national":
        return f"0{rng.choice(['85', '86', '87', '89'])} {digits(3)} {digits(4)}"
    if style == "intl":
        return f"+353 {rng.choice(['85', '86', '87', '89'])} {digits(3)} {digits(4)}"
    return f"+44{digits(10)}"


KIND_GEN = {
    "email address": gen_email,
    "card number": gen_card,
    "IBAN": gen_iban,
    "PPSN": gen_ppsn,
    "phone number": gen_phone,
}

# ---------- negative generators: each returns text that is NOT personal data ----------

def neg_order_id():
    return f"order_id={rng.randint(10**9, 10**10 - 1)}"


def neg_timestamp():
    return (f"ts=2026-10-{rng.randint(1, 28):02d}T{rng.randint(0, 23):02d}:"
            f"{rng.randint(0, 59):02d}:{rng.randint(0, 59):02d}")


def neg_request_id():
    return f"request_id={uuid.uuid4()}"


def neg_bad_luhn_card():
    good = add_luhn_digit("4" + digits(14))
    bad_last = str((int(good[-1]) + 1) % 10)
    return f"card_fp={good[:-1] + bad_last}"


def neg_bad_iban_check():
    good = make_iban("IE", "AIBK" + digits(14))
    return f"iban_ref={good[:2]}{(int(good[2:4]) + 1) % 100:02d}{good[4:]}"


def neg_short_numbers():
    return f"retry={rng.randint(1, 9)} batch={rng.randint(100, 99999)}"


def neg_sku_looks_like_ppsn():
    # Deliberately PPSN-shaped, but a product code, not a PPSN.
    return f"sku={digits(7)}{rng.choice('ABCDE')}"


def neg_leading_zero_batch():
    # Starts with 0 and has 10 digits, so it looks like a national phone number.
    return f"batch=0{digits(9)}"


def neg_plain_text():
    return rng.choice(["GET /health 200 12ms", "cache miss for key settings_v2",
                       "job finished in 4.2s"])


NEG_GENERATORS = [neg_order_id, neg_timestamp, neg_request_id, neg_bad_luhn_card,
                  neg_bad_iban_check, neg_short_numbers, neg_sku_looks_like_ppsn,
                  neg_leading_zero_batch, neg_plain_text]

# ---------- line templates ----------
# "@@TS@@" is replaced by a timestamp first, then {a}/{b} by values.
# Timestamps are replaced before values, so random values can't disturb them.

TEMPLATES = [
    "@@TS@@ INFO  user contact={a}",
    "@@TS@@ WARN  request failed, value={a}",
    '@@TS@@ DEBUG payload={"v":"{a}"}',
    "@@TS@@ INFO  sent to {a} ok",
    "@@TS@@ ERROR parse error near {a}",
]
TWO_VALUE_TEMPLATE = "@@TS@@ INFO  notify {a} and {b}"

# Lines where personal data is present but written in a way the scanner
# is not designed to catch. These are labelled honestly, so they show up as misses.
HARD_POSITIVES = [
    ("@@TS@@ INFO  card=4111.1111.1111.1111", ["card number"]),
    ("@@TS@@ INFO  iban=gb82west12345698765432", ["IBAN"]),
    ("@@TS@@ INFO  contact jane dot doe at example dot test", ["email address"]),
    ("@@TS@@ INFO  ppsn=1234567-T", ["PPSN"]),
    ("@@TS@@ INFO  ppsn=1234567 T", ["PPSN"]),
]


def ts_for(i):
    return f"2026-10-14T09:{(i // 60) % 60:02d}:{i % 60:02d}Z"


def make_positive(i):
    ts = ts_for(i)
    if rng.random() < 0.25:
        kinds = rng.sample(list(KIND_GEN), 2)
        line = (TWO_VALUE_TEMPLATE.replace("@@TS@@", ts)
                .replace("{a}", KIND_GEN[kinds[0]]())
                .replace("{b}", KIND_GEN[kinds[1]]()))
    else:
        kinds = [rng.choice(list(KIND_GEN))]
        line = (rng.choice(TEMPLATES).replace("@@TS@@", ts)
                .replace("{a}", KIND_GEN[kinds[0]]()))
    return {"line": line, "expected": kinds}


def make_negative(i):
    ts = ts_for(i)
    text = rng.choice(NEG_GENERATORS)()
    return {"line": f"{ts} INFO  {text}", "expected": []}


def main():
    rows = [make_positive(i) for i in range(150)]
    rows += [make_negative(i) for i in range(150, 270)]
    rows += [{"line": text.replace("@@TS@@", ts_for(270 + i)), "expected": kinds}
             for i, (text, kinds) in enumerate(HARD_POSITIVES)]

    OUT.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows),
                   encoding="utf-8")
    positives = sum(1 for r in rows if r["expected"])
    print(f"Wrote {len(rows)} lines to {OUT.name} "
          f"({positives} with personal data, {len(rows) - positives} without)")


if __name__ == "__main__":
    main()
