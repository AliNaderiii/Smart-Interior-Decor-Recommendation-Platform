#!/usr/bin/env python3
"""Quantify the `Lighthouse report secret scan` false-positive rate.

The CI step greps Lighthouse report JSON for credential patterns. One
alternative, `sk-[A-Za-z0-9]{20,}`, matches random base64url content — and the
reports embed session JWTs (base64url) many times over. This script measures
how often that happens by chance.

    $ python3 falsepositive_probability.py
    random-base64url false-positive rate: 288/200000 = 0.14400% per 700 chars
"""
import re
import secrets
import string

PATTERN = re.compile(
    r"(BEGIN (RSA|OPENSSH|EC|PRIVATE) KEY"
    r"|ghp_[A-Za-z0-9]{36}"
    r"|sk-[A-Za-z0-9]{20,}"
    r"|AIza[0-9A-Za-z_-]{35})"
)
ALPHABET = string.ascii_letters + string.digits + "-_"   # base64url
TRIALS = 200_000
TOKEN_TRIO_CHARS = 700    # access + refresh + csrf, roughly


def main() -> None:
    hits = sum(
        1
        for _ in range(TRIALS)
        if PATTERN.search(
            "".join(secrets.choice(ALPHABET) for _ in range(TOKEN_TRIO_CHARS))
        )
    )
    p = hits / TRIALS
    print(f"random-base64url false-positive rate: {hits}/{TRIALS} "
          f"= {p:.5%} per {TOKEN_TRIO_CHARS} chars")
    for reps in (12, 60, 200, 1000):
        print(f"  probability over {reps:>4} embeddings in a run: "
              f"{1 - (1 - p) ** reps:.2%}")


if __name__ == "__main__":
    main()
