"""Run an embedded PostgreSQL (with pgvector) for local parity testing.

Uses the `pgserver` wheel — a self-contained Postgres 16 + pgvector build —
so the Postgres code path (fused `<=>` query, HNSW index migration) can be
exercised without Docker.

Usage:
    python scripts/dev_postgres.py [datadir]

Prints the SQLAlchemy DATABASE_URL and keeps the server alive until killed.
"""
from __future__ import annotations

import signal
import sys
import time

import pgserver


def main() -> None:
    datadir = sys.argv[1] if len(sys.argv) > 1 else "/tmp/pgdev"
    server = pgserver.get_server(datadir, cleanup_mode=None)
    server.psql("CREATE EXTENSION IF NOT EXISTS vector;")
    uri = server.get_uri()
    host = uri.split("host=")[1]
    print("postgres ready (pgvector installed)", flush=True)
    print(f"DATABASE_URL=postgresql+psycopg://postgres:@/postgres?host={host}", flush=True)
    print("create databases with: psql or server.psql(...)", flush=True)

    stop = []
    signal.signal(signal.SIGTERM, lambda *_: stop.append(1))
    signal.signal(signal.SIGINT, lambda *_: stop.append(1))
    while not stop:
        time.sleep(1)
    server.cleanup()


if __name__ == "__main__":
    main()
