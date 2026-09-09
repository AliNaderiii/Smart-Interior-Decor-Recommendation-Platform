"""Feed adapters: each yields plain mappings that :func:`contract.normalize_row` accepts.

* :mod:`.file` — CSV / JSON files a seller exports (documented template in
  ``seed_data/feed_template.csv``);
* :mod:`.basalam` — the official Basalam Open API (``openapi.basalam.com``).
"""
