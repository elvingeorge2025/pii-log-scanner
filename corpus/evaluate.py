#!/usr/bin/env python3
"""Compare the scanner's output with the labels in labelled_corpus.jsonl.

For each kind of personal data:
    true positive  = scanner found it and the label says it is there
    false positive = scanner reported it, but the label says it is not there
    miss           = the label says it is there, but the scanner did not find it
"""
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
import pii_scanner as ps  # noqa: E402


def ratio(num, den):
    return f"{num / den:.0%}" if den else "n/a"


def main():
    path = HERE / "labelled_corpus.jsonl"
    rows = [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]

    stats = defaultdict(Counter)
    failures = []
    exact = 0

    for row in rows:
        expected = Counter(row["expected"])
        predicted = Counter(kind for _, _, kind in ps.find_spans(row["line"]))
        for kind in set(expected) | set(predicted):
            e, p = expected[kind], predicted[kind]
            stats[kind]["tp"] += min(e, p)
            stats[kind]["fp"] += max(p - e, 0)
            stats[kind]["miss"] += max(e - p, 0)
        if expected == predicted:
            exact += 1
        else:
            failures.append((row, expected, predicted))

    print(f"Corpus: {len(rows)} lines\n")
    print(f"{'Kind':<16}{'TP':>5}{'FP':>5}{'Miss':>6}{'Precision':>11}{'Recall':>9}")
    print("-" * 52)
    total = Counter()
    for kind in sorted(stats):
        s = stats[kind]
        total.update(s)
        print(f"{kind:<16}{s['tp']:>5}{s['fp']:>5}{s['miss']:>6}"
              f"{ratio(s['tp'], s['tp'] + s['fp']):>11}"
              f"{ratio(s['tp'], s['tp'] + s['miss']):>9}")
    print("-" * 52)
    print(f"{'All':<16}{total['tp']:>5}{total['fp']:>5}{total['miss']:>6}"
          f"{ratio(total['tp'], total['tp'] + total['fp']):>11}"
          f"{ratio(total['tp'], total['tp'] + total['miss']):>9}")
    print(f"\nLines exactly right: {exact} of {len(rows)} ({ratio(exact, len(rows))})")

    print(f"\nFailing lines ({len(failures)}):")
    for row, expected, predicted in failures:
        print(f"  expected {dict(expected) or 'nothing'}, scanner said {dict(predicted) or 'nothing'}")
        print(f"    {row['line']}")


if __name__ == "__main__":
    main()
