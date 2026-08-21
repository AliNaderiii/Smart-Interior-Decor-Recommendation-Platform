"""Log redaction (OWASP A09 — Logging Failures / GDPR data minimisation).

Two independent problems this solves.

**Secrets in logs.** `httpx`, `boto3`, `sqlalchemy` and our own code all log
URLs and, on failure, request context. Those strings can contain a Gemini API
key (`?key=…`), a payment `authority`, a bearer token or a raw JWT. Anything
written to stdout is shipped to whatever aggregator the client runs and is then
outside the application's access control.

**Personal data in logs.** The brute-force module logged the attempted email
address at WARNING on every lockout::

    brute-force lockout engaged for email=victim@example.com ip=1.2.3.4

That is an authentication-failure log containing an account identifier, kept
for as long as the log retention allows, with none of the access controls that
protect the `users` table. Stage 03 probe `P-01` observed it verbatim.

Policy
------
* Token-shaped material is replaced with a fixed marker — never truncated,
  because a prefix of a JWT still identifies the session.
* Email addresses become ``a***@example.com`` plus a short salted digest, so
  operators keep the ability to correlate "the same account across events"
  without the log holding the address itself. The salt is the application
  ``SECRET_KEY``: correlation works within a deployment and does not survive
  key rotation, which is exactly the property a pseudonym should have.
* The filter is attached to the **root** logger's handlers and to uvicorn's, so
  it applies to third-party libraries that this project does not control.

The filter mutates ``record.msg``/``record.args`` after formatting rather than
wrapping every call site: a redaction control that depends on every future
developer remembering it is not a control.
"""
from __future__ import annotations

import hashlib
import hmac
import logging
import re

_JWT_RE = re.compile(r"\beyJ[A-Za-z0-9_-]{5,}\.[A-Za-z0-9_-]{5,}\.[A-Za-z0-9_-]{5,}\b")
_BEARER_RE = re.compile(r"(?i)\b(bearer|basic)\s+[A-Za-z0-9._\-+/=]{8,}")
_QUERY_SECRET_RE = re.compile(
    r"(?i)\b(api[_-]?key|access[_-]?key|secret|token|password|passwd|pwd|"
    r"authority|signature|sig|key)\s*[=:]\s*[\"']?([^\s\"'&,;)]{4,})"
)
_HEADER_SECRET_RE = re.compile(
    r"(?i)\b(authorization|cookie|set-cookie|x-csrf-token)\b\s*[:=]\s*[^\s,;]{4,}"
)
_EMAIL_RE = re.compile(r"\b([A-Za-z0-9._%+\-]+)@([A-Za-z0-9.\-]+\.[A-Za-z]{2,})\b")
_PAN_RE = re.compile(r"\b(?:\d[ -]?){13,19}\b")

REDACTED = "[REDACTED]"


def pseudonymise_email(email: str) -> str:
    """``victim@example.com`` -> ``v***@example.com#a1b2c3d4`` (keyed digest)."""
    from app.core.config import settings

    local, _, domain = email.partition("@")
    digest = hmac.new(
        settings.SECRET_KEY.encode(), email.lower().encode(), hashlib.sha256
    ).hexdigest()[:8]
    head = local[:1] if local else "?"
    return f"{head}***@{domain or '?'}#{digest}"


def redact(text: str) -> str:
    """Remove credentials and personal identifiers from a log line."""
    if not text:
        return text
    text = _JWT_RE.sub(f"{REDACTED}-jwt", text)
    text = _BEARER_RE.sub(lambda m: f"{m.group(1)} {REDACTED}", text)
    text = _HEADER_SECRET_RE.sub(lambda m: f"{m.group(1)}: {REDACTED}", text)
    text = _QUERY_SECRET_RE.sub(lambda m: f"{m.group(1)}={REDACTED}", text)
    text = _EMAIL_RE.sub(lambda m: pseudonymise_email(m.group(0)), text)
    text = _PAN_RE.sub(lambda m: REDACTED if _looks_like_pan(m.group(0)) else m.group(0), text)
    return text


def _looks_like_pan(candidate: str) -> bool:
    """Luhn check, so ordinary long numbers (ids, prices) are not mangled."""
    digits = [int(c) for c in candidate if c.isdigit()]
    if not 13 <= len(digits) <= 19:
        return False
    checksum, parity = 0, len(digits) % 2
    for index, digit in enumerate(digits):
        if index % 2 == parity:
            digit *= 2
            if digit > 9:
                digit -= 9
        checksum += digit
    return checksum % 10 == 0


class RedactingFilter(logging.Filter):
    """Redact the fully-rendered message of every record passing through.

    Kept as a public class because a `logging.Filter` is what most operators
    reach for, but note the limitation that motivated the record-factory
    approach below: a filter attached to a *logger* only sees records emitted
    through that logger, and a filter attached to a *handler* only protects
    that handler. Any handler added later — by a test, by an APM agent, by
    `logging.basicConfig` being called again — would see raw text.
    """

    def filter(self, record: logging.LogRecord) -> bool:  # noqa: A003
        _redact_record(record)
        return True


def _redact_record(record: logging.LogRecord) -> None:
    try:
        rendered = record.getMessage()
    except Exception:  # pragma: no cover - malformed args
        return
    cleaned = redact(rendered)
    if cleaned != rendered:
        record.msg = cleaned
        record.args = ()


_INSTALLED = False
_PREVIOUS_FACTORY = None


def install_log_redaction() -> None:
    """Redact at record-creation time, so *every* handler is covered.

    `logging.setLogRecordFactory` is the only hook that runs before any handler
    — including handlers installed after this call — which is what makes the
    control hold in production, where an APM/agent sidecar routinely attaches
    its own handler at import time.
    """
    global _INSTALLED, _PREVIOUS_FACTORY
    if _INSTALLED:
        return
    _PREVIOUS_FACTORY = logging.getLogRecordFactory()

    def factory(*args, **kwargs):
        record = _PREVIOUS_FACTORY(*args, **kwargs)
        _redact_record(record)
        return record

    logging.setLogRecordFactory(factory)

    # Belt and braces for handlers that build records themselves.
    log_filter = RedactingFilter()
    root = logging.getLogger()
    for handler in root.handlers:
        handler.addFilter(log_filter)
    _INSTALLED = True


def reset_log_redaction_for_tests() -> None:  # pragma: no cover - test helper
    global _INSTALLED
    if _INSTALLED and _PREVIOUS_FACTORY is not None:
        logging.setLogRecordFactory(_PREVIOUS_FACTORY)
    _INSTALLED = False

