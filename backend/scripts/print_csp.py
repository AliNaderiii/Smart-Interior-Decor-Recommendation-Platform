#!/usr/bin/env python
"""Print the Content-Security-Policy for the Caddyfile proxy copy (T-2.4).

``build_csp()`` in app/core/security_headers.py is the single source of truth
for the CSP. The Caddyfile mirrors it for defence in depth, and
``tests/test_csp_alignment.py`` fails when the two drift. After changing any
image-host setting (S3_ENDPOINT, S3_PUBLIC_BASE_URL, IMAGE_CDN_BASE_URL,
IMAGE_EXTRA_ORIGINS), regenerate the proxy copy:

    # The reference production deployment (Arvan endpoint, as documented in
    # .env.example) — this is what the committed Caddyfile must contain:
    python scripts/print_csp.py --reference

    # Your actual environment (reads the same env vars the app reads):
    python scripts/print_csp.py

Paste the output between the quotes of the ``Content-Security-Policy``
directive in the Caddyfile ``header`` block.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.security_headers import build_csp  # noqa: E402

#: The deployment documented in .env.example: Arvan S3 endpoint, production.
#: Kept as a plain namespace so printing the reference never requires
#: production-grade secrets in the environment.
REFERENCE_CFG = type("ReferenceCfg", (), {
    "S3_PUBLIC_BASE_URL": "",
    "S3_ENDPOINT": "https://s3.ir-thr-at1.arvanstorage.ir",
    "IMAGE_CDN_BASE_URL": "",
    "IMAGE_EXTRA_ORIGINS": "",
    "is_production": True,
})()


def main() -> None:
    if "--reference" in sys.argv:
        print(build_csp(REFERENCE_CFG))
    else:
        print(build_csp())


if __name__ == "__main__":
    main()
