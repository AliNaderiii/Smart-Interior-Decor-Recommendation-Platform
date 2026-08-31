"""BUG-401 regression: no value-side inline comments in ``.env.example``.

Docker Compose's ``env_file`` does not strip inline ``#`` comments from
values, so a template line like ``DEMO_ACCOUNT_PASSWORD=  # [OPTIONAL]
test-only override`` seeded every demo account with the comment string as its
password. This test pins the *whole* template: every assignment must carry its
documentation on a dedicated comment line, never as a value-side ``# comment``.
If a value-side comment is reintroduced anywhere in the file, this fails CI.
"""
from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
ENV_EXAMPLE = REPO_ROOT / ".env.example"

# An "assignment" line starts with VARNAME= ; a value-side inline comment is a
# `#` appearing anywhere after the `=`. No value in this file legitimately
# contains `#` (no URL fragments), so any hit is a bug. This is deliberately
# *wider* than the supervisor's relayed pattern so the empty-value case
# (`KEY=  # comment`) is also caught.
ASSIGNMENT_WITH_COMMENT = re.compile(r"^[A-Z0-9_]+\s*=.*#")

# The supervisor's verification pattern (ruling S5-R0): the subset of cases
# where a non-empty value is followed by an inline comment.
SUPERVISOR_PATTERN = re.compile(r"^[A-Z0-9_]+\s*=\s*\S.*#")


def test_env_example_has_no_value_side_inline_comments():
    text = ENV_EXAMPLE.read_text(encoding="utf-8")
    hits = [ln for ln in text.splitlines() if ASSIGNMENT_WITH_COMMENT.match(ln)]
    assert hits == [], (
        "value-side inline comments found in .env.example (BUG-401): "
        + "; ".join(repr(h) for h in hits)
    )


def test_env_example_supervisor_pattern_is_clean():
    text = ENV_EXAMPLE.read_text(encoding="utf-8")
    hits = [ln for ln in text.splitlines() if SUPERVISOR_PATTERN.match(ln)]
    assert hits == [], (
        "supervisor pattern matches: " + "; ".join(repr(h) for h in hits)
    )


def test_env_example_still_defines_the_expected_keys():
    """Guard against a regression test that passes only because the file shrank."""
    text = ENV_EXAMPLE.read_text(encoding="utf-8")
    for key in (
        "APP_ENV",
        "SECRET_KEY",
        "DEMO_ACCOUNT_PASSWORD",
        "SEED_DEMO_ACCOUNTS",
        "DATABASE_URL",
        "AI_PROVIDER",
    ):
        assert re.search(rf"^{key}=", text, flags=re.M), f"{key}= missing"
