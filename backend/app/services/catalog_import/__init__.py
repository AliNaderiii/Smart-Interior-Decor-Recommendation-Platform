"""Seller-feed importer (P4-ب item 2, builds on ADR-016).

A sold deployment needs a catalog of **real** products: the seller's own photo,
a dated price and a deep link to the product page. Nothing in this package
invents a value — every field either comes from the seller feed or is left
empty so the integrity gate (:mod:`ai.catalog_integrity`) can refuse the row.

Layout::

    contract.py   FeedRow — the source-agnostic input contract + normaliser
    adapters/     file (CSV/JSON) and basalam (official OpenAPI) → FeedRow
    images.py     SSRF-guarded download → validate → pHash → own storage
    pipeline.py   FeedRow → Product (upsert by source/source_product_id),
                  vision detected_category, embedding, integrity stamp, report

The CLI lives in ``scripts/import_catalog.py``.
"""
