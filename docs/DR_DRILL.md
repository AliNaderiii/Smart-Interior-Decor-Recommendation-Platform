# Disaster Recovery & Database Restoration Drill (`DR_DRILL.md`)

**Document Version:** 1.0 (Stage 3 Delivery)  
**Target Architecture:** PostgreSQL 16 + pgvector, Redis, Docker Compose / Host Deployment  
**Lead Role:** SA-6 (Resilience / Postgres SRE)  
**Objectives:** RPO ≤ 24 hours, RTO ≤ 30 minutes

---

## 1. Overview & Policy

This procedure defines the end-to-end operational sequence to restore the platform database from an automated logical dump in the event of hardware failure, catastrophic data corruption, or staging environment reproduction.

* **Format:** Logical pg_dump in PostgreSQL Custom Archive format (`-Fc`), compressed with level 6 gzip.
* **Retention:** 14 daily backup snapshots maintained on host; replicated to off-site cloud object storage (`s3://smartdecor-backups/`).
* **Integrity Guard:** Every backup verifies format completeness and file size > 0.
* **Encryption / PII:** Audits and payment records preserved under statutory obligations; user secrets and passwords hashed with bcrypt; KMS-managed Fernet key required for sensitive columns.

---

## 2. Automated Backup Execution

### Cron Schedule (Stage 4 / Production Host)
```crontab
# Daily backup at 02:30 UTC
30 2 * * * cd /opt/decor && ./scripts/backup_db.sh /var/backups/smartdecor 14 >> /var/log/decor-backup.log 2>&1
```

### Manual Backup Command
```bash
./scripts/backup_db.sh ./backups 14
```

---

## 3. Step-by-Step Restoration Drill

### Step 1: Locate and Validate Backup Archive
```bash
# List available backups and pick the desired snapshot
ls -lh backups/smartdecor_db_*.dump

# Validate archive header with pg_restore list
pg_restore -l backups/smartdecor_db_20260828_023000Z.dump | head -n 20
```

### Step 2: Provision / Clean Scratch Target Database
```bash
# Connect to PostgreSQL instance
psql -U decor -d postgres -c "CREATE DATABASE decor_scratch;"
psql -U decor -d decor_scratch -c "CREATE EXTENSION IF NOT EXISTS vector;"
```

### Step 3: Execute pg_restore
```bash
# Run restore into target scratch database
./scripts/restore_db.sh backups/smartdecor_db_20260828_023000Z.dump decor_scratch
```

### Step 4: Verification Queries (Integrity, Row Counts, pgvector Index)
Execute the following verification script:
```sql
-- Connect to restored database
\c decor_scratch

-- 1. Table Row Counts Check
SELECT 'users' AS tbl, count(*) FROM users
UNION ALL
SELECT 'products', count(*) FROM products
UNION ALL
SELECT 'moodboards', count(*) FROM moodboards
UNION ALL
SELECT 'style_quizzes', count(*) FROM style_quizzes;

-- 2. pgvector Extension and Index Sanity
SELECT extname, extversion FROM pg_extension WHERE extname = 'vector';

-- 3. Vector Distance Query Verification (<=> operator)
SELECT id, title, category,
       (style_embedding <=> '[0.01, 0.02, 0.03, ...]'::vector) AS dist
FROM products
WHERE style_embedding IS NOT NULL
ORDER BY dist ASC
LIMIT 5;
```

---

## 4. Disaster Recovery Drill Success Criteria

| Criterion | Target Metric | Verification Method |
|---|---|---|
| **Archive Readability** | 0 parsing errors | `pg_restore -l` exits with return code 0. |
| **Schema Integrity** | 100% tables and indexes restored | All tables (`users`, `products`, `moodboards`, `projects`, `audit_logs`) present. |
| **Data Parity** | 0 missing rows vs backup manifest | Row counts match source dump counts. |
| **Vector Engine Functionality** | 100% vector queries succeed | `<=>` fused cosine distance query executes with HNSW index utilization. |
| **Application Serving** | 200 OK on health and recommend APIs | Pointing backend `DATABASE_URL` to restored database serves valid recommendations. |
