"""Payment gateway abstraction — Zarinpal / Zibal, sandbox first.

We only ever store the gateway *authority* (redirect token) and the final
*ref_id*. No card data ever touches this system (acceptance criterion).
"""
from __future__ import annotations

import uuid
from abc import ABC, abstractmethod

import httpx

from app.core.config import settings

PRO_PLAN_PRICE_TOMAN = 490_000


class PaymentGateway(ABC):
    @abstractmethod
    def request_payment(self, amount_toman: int, description: str) -> tuple[str, str]:
        """Return (authority, redirect_url)."""

    @abstractmethod
    def verify_payment(self, authority: str, amount_toman: int) -> tuple[bool, str]:
        """Return (paid, ref_id)."""


class ZarinpalGateway(PaymentGateway):
    """Zarinpal REST v4. Sandbox and production differ only by base URL."""

    def __init__(self, sandbox: bool = True) -> None:
        self.base = (
            "https://sandbox.zarinpal.com/pg/v4/payment"
            if sandbox
            else "https://payment.zarinpal.com/pg/v4/payment"
        )
        self.pay_base = (
            "https://sandbox.zarinpal.com/pg/StartPay"
            if sandbox
            else "https://payment.zarinpal.com/pg/StartPay"
        )

    def request_payment(self, amount_toman: int, description: str) -> tuple[str, str]:
        resp = httpx.post(
            f"{self.base}/request.json",
            json={
                "merchant_id": settings.ZARINPAL_MERCHANT_ID,
                "amount": amount_toman * 10,  # Zarinpal uses Rial
                "description": description,
                "callback_url": settings.PAYMENT_CALLBACK_URL,
            },
            timeout=30,
        )
        resp.raise_for_status()
        authority = resp.json()["data"]["authority"]
        return authority, f"{self.pay_base}/{authority}"

    def verify_payment(self, authority: str, amount_toman: int) -> tuple[bool, str]:
        resp = httpx.post(
            f"{self.base}/verify.json",
            json={
                "merchant_id": settings.ZARINPAL_MERCHANT_ID,
                "amount": amount_toman * 10,
                "authority": authority,
            },
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json().get("data") or {}
        return data.get("code") in (100, 101), str(data.get("ref_id", ""))


class MockGateway(PaymentGateway):
    """Offline gateway for dev/tests — instantly 'paid'."""

    def request_payment(self, amount_toman: int, description: str) -> tuple[str, str]:
        authority = f"MOCK-{uuid.uuid4().hex[:24]}"
        return authority, f"{settings.PAYMENT_CALLBACK_URL}?Authority={authority}&Status=OK"

    def verify_payment(self, authority: str, amount_toman: int) -> tuple[bool, str]:
        return authority.startswith("MOCK-"), f"REF-{authority[-8:]}"


def get_gateway() -> PaymentGateway:
    provider = settings.PAYMENT_PROVIDER
    if provider == "zarinpal":
        return ZarinpalGateway(sandbox=False)
    if provider == "zarinpal_sandbox":
        return ZarinpalGateway(sandbox=True)
    # zibal support lands post-MVP behind this same interface
    return MockGateway()
