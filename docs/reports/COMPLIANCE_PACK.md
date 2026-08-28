# Compliance & Privacy Assurance Pack (`COMPLIANCE_PACK.md`)

**Date:** 2026-08-28  
**Scope:** Smart Interior Decor Recommendation Platform (HEAD / v0.6.0+Stage 3)  
**Lead Auditors:** SA-4 (Infra & Security Engineer) & SA-5 (Compliance & Privacy Auditor)  
**Standard Mappings:** GDPR (EU 2016/679), OWASP Top 10 (2021), PCI-DSS SAQ-A Equivalent, TLS 1.3 Baseline

---

## 1. Executive Summary & Attestations

| Requirement | Platform Implementation | Verification / Code Pointer | Status |
|---|---|---|---|
| **TLS 1.3 Everywhere** | Caddy reverse proxy enforces TLS 1.3 exclusively (`protocols tls1.3 tls1.3`) on `:443`; automatic HTTP->HTTPS permanent redirect on `:80`. | `Caddyfile:11-13`, `Caddyfile:58-60` | **VERIFIED** |
| **Password Hashing** | bcrypt with work factor 12 via `passlib[bcrypt]`; input length bounded to 72 bytes. | `backend/app/core/security.py:27-38` | **VERIFIED** |
| **Encryption-at-Rest** | Symmetric authenticated Fernet encryption abstraction with cloud KMS migration path. | `backend/app/core/security.py:84-118` | **VERIFIED** |
| **No Card Data Stored** | Zero PAN/CVV storage; payment intent redirect to Iranian payment gateways (Zarinpal/Zibal) with opaque token callback verification. | `backend/app/services/payment.py:1-85`, `app/api/routes/subscriptions.py:44-77` | **ATTESTED** |
| **GDPR Art. 15 (Access)** | Machine-readable JSON export of all personal data (`GET /api/v1/users/me/export`). | `backend/app/api/routes/users.py:59-145` | **VERIFIED** |
| **GDPR Art. 17 (Erasure)** | Hard deletion of user account, cascading erasure across quizzes, moodboards, projects, share links, and Redis cache invalidation (`rec:{uid}:*`); security audit logs pseudonymised. | `backend/app/api/routes/users.py:148-220` | **VERIFIED** |
| **Audit Retention** | Security audit events retained for 180 days under GDPR Art. 6(1)(f); automated daily pruning loop. | `backend/scripts/prune_audit_logs.py`, `docker-compose.prod.yml:68-81` | **VERIFIED** |

---

## 2. GDPR Compliance Matrix & Data Map

### 2.1 Personal Data Inventory (PII Map)

| Data Category | Storage Location | Retention Period | Legal Basis | Erasure Behavior (Art. 17) |
|---|---|---|---|---|
| **User Identity** (`email`, `full_name`, `hashed_password`) | `users` table | Account lifetime | Contract (Art. 6.1.b) | **Hard Deleted** |
| **Quiz Preferences** (`styles`, `color_palette`, `budget`) | `style_quizzes` table | Account lifetime | Consent / Contract | **Hard Deleted** |
| **Moodboards & Layouts** | `moodboards` table | Account lifetime | Contract (Art. 6.1.b) | **Hard Deleted** |
| **Designer Projects & Share Tokens** | `projects`, `share_links` | Project lifetime / Expire TTL | Contract (Art. 6.1.b) | **Hard Deleted** |
| **Product Feedback** (`signal`, `product_id`) | `product_feedback` | Account lifetime | Consent / Contract | **Hard Deleted** |
| **Payment Records** (`amount_toman`, `authority`, `ref_id`) | `payments` table | 7 years (Statutory) | Legal Obligation (Art. 6.1.c) | **Pseudonymised** (user_id severed) |
| **Security Audit Logs** (`ip`, `user_agent`, `action`) | `audit_logs` table | 180 days | Legitimate Interest (Art. 6.1.f) | **Pseudonymised** (IP truncated to /24, UA cleared, ID keyed-HMAC digest) |
| **Recommendation Cache** | Redis (`rec:{user_id}:*`) | 1 hour TTL | Performance / Contract | **Purged Immediately** upon account deletion |

### 2.2 Data Flow Architecture Diagram

```
[ Visitor / Client Browser ]
           │
           │ (HTTPS / TLS 1.3 enforced)
           ▼
[ Caddy Reverse Proxy ] ─── (Strict Security Headers + CSP + HSTS)
           │
           ├───────────────┬─────────────────┐
           ▼               ▼                 ▼
   [ Static SPA ]    [ FastAPI API ]   [ Prometheus ]
   (Nginx non-root)        │            (/metrics)
                           ├────────────────────────┐
                           ▼                        ▼
                 [ PostgreSQL 16 + pgvector ]  [ Redis 7.4 ]
                 (Hashed Passwords / KMS)      (Blacklist / Throttles)
```

---

## 3. Cryptographic Controls & Key Management Posture

1. **Password Storage:** bcrypt with cryptographic work factor (`app/core/security.py`).
2. **JWT Sessions:** Signed with `HS256` using high-entropy `SECRET_KEY` (minimum 256 bits). PyJWT pins allowed algorithms to HMAC family; `alg: "none"` is rejected unconditionally. Access token TTL = 15 minutes; Refresh token TTL = 7 days with rotation and single-use Redis revocation (`jti`).
3. **Encryption at Rest:** Symmetric Fernet authenticated encryption abstraction (`KMSClient`).
4. **Cloud KMS Migration Path:**
   - *Current MVP:* Encrypted with key loaded from `FERNET_KEY` env var.
   - *Production KMS Target:* Drop-in replacement with AWS KMS / Arvan Vault envelope encryption via the existing `encrypt_at_rest()` and `decrypt_at_rest()` interfaces in `app/core/security.py`.

---

## 4. Payment Gateway & "No Card Data" Attestation

The Smart Interior Decor Recommendation Platform does **not** collect, process, transmit, or store credit/debit card numbers (PAN), expiration dates, CVVs, or cardholder banking credentials.

* **Redirect Flow:** User selects subscription upgrade -> platform requests transaction authority from Iranian gateway (Zarinpal/Zibal) -> user is redirected to official Shaparak banking portal (`app/services/payment.py`).
* **Server Verification:** Callback receives opaque `authority` string and confirms payment server-to-server.
* **Database State:** `payments` table records only `authority`, `ref_id`, `amount_toman`, and `status`.

---

## 5. Client Decisions Register (C-Items)

| Item ID | Topic | Description & Options | Recommended Action |
|---|---|---|---|
| **C-01** | Cloud KMS Provider | Selection between AWS KMS, HashiCorp Vault, or Iranian Cloud (ArvanCloud Vault) for production key envelope management. | Adopt HashiCorp Vault / Cloud KMS in Stage 4 deployment. |
| **C-02** | Audit Log Retention | Confirming 180-day retention window for cybersecurity audit logs vs. client internal compliance policy. | Retain 180-day default under GDPR Art. 6(1)(f). |
| **C-03** | Third-Party Shop Egress | Policy on live seller link checking frequency against Iranian retailer anti-bot scrapers. | Run advisory periodic sweep (1 req/s rate limit). |
