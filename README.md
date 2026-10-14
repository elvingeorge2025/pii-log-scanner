# pii-log-scanner

Applications often write personal data into logs by accident: email addresses, phone numbers, card numbers, bank details. Logs get copied, kept for long periods, and read by people who should not see that data. This tool scans log files and reports where personal data appears, without printing the values.

## Usage

Python 3.9+, standard library only.

```bash
python pii_scanner.py samples/app.log
python pii_scanner.py samples/app.log --redact-dir clean/
python -m unittest -v
```

Example output:

```
samples/app.log: card number detected at line 3, value masked
samples/app.log: IBAN detected at line 4, value masked
...
```

The exit status is 0 when nothing is found and 1 when something is found, so it can run in CI. With `--redact-dir`, a copy of each file is written with matches replaced by labels such as `[REDACTED:CARD_NUMBER]`.

## Detection rules

| Kind | Method | Validation |
|---|---|---|
| IBAN | Regex for country code, check digits and BBAN | ISO 13616 mod-97 check |
| Card number | 13 to 19 digits, optional spaces or dashes | Luhn checksum |
| Email address | Regex | None beyond format |
| PPSN (Irish) | 7 digits, one letter, optional second letter | Format only |
| Phone number | Starts with `+`, or starts with `0` and uses spaces, dashes or brackets; 9 to 15 digits | Length, prefix and separators |

Matches are checked in the order above. A value claimed by one detector is not reported again by another. A card number, for example, is never also reported as a phone number.

## Testing

Test data is generated or made up. IBANs are built by the test helper, which computes valid check digits. Card numbers are the standard public test numbers. PPSN-shaped values are invented. No value corresponds to a real person.

The unit tests cover validators, each detector, negative cases (order IDs, timestamps), redaction, and the sample file. Run them with `python -m unittest -v`.

The unit tests show that the rules work on the cases I wrote. They do not measure real-world accuracy, which is what the labelled corpus below is for.

## Results

Measured on `corpus/labelled_corpus.jsonl`: 275 synthetic lines. The labels were written before testing, but the phone rule was adjusted after the first run on this same set, so the phone results are optimistic. Regenerate the corpus with `python3 corpus/generate_corpus.py` and check it with `python3 corpus/evaluate.py`.

The corpus includes 120 lines with no personal data and 5 deliberate hard cases.

| Kind | True positives | False positives | Misses | Precision | Recall |
|---|---|---|---|---|---|
| IBAN | 41 | 0 | 1 | 100% | 98% |
| Card number | 44 | 0 | 1 | 100% | 98% |
| Email address | 37 | 0 | 1 | 100% | 97% |
| PPSN | 38 | 16 | 2 | 70% | 95% |
| Phone number | 27 | 0 | 0 | 100%* | 100%* |
| **All** | **187** | **16** | **5** | **92%** | **97%** |

\* Optimistic, for the reason given above.

254 of 275 lines were classified exactly right (92%).

The corpus was written alongside the scanner and contains deliberate hard cases, so these numbers describe how the scanner handles those cases. They do not predict performance on real logs.

## Limitations

- **PPSN false positives.** The pattern matches any 7 digits followed by a letter, including some strings that are not PPSNs. The check character algorithm is not implemented, so a format match is not proof of a real PPSN.
- **Free text is not detected.** Names, addresses and other personal data without a recognisable format are not found. A name such as "Jane Doe" in a log line will not be flagged.
- **Phone trade-off.** National numbers written without separators (for example `0851234567`) are not detected. Without this rule, batch and reference numbers starting with `0` were flagged as phone numbers: 13 false alarms in the test set. Dropping the rule trades these misses for false alarms, so real logs may need a different balance.
- **Card detection can false-positive.** About 1 in 10 random digit strings of the right length pass Luhn. The check is one filter, not proof.
- **Missed formats.** Values written with dots, lowercase IBANs, emails written out in words, and PPSNs with a dash or space are not detected, as the corpus shows.
- **Encoding.** Files are read as UTF-8 with replacement characters for invalid bytes. Binary logs are not supported.
- **Split values.** A value broken across two lines is not detected.

## Ethics and data handling

- Use only synthetic test data. Do not run this against real logs for testing or publish real logs or sample output from them.
- Reports contain file names, line numbers and kinds only. Values are never printed.
- Do not add real personal data to the samples or tests.

## Licence

MIT. See [LICENSE](LICENSE).
