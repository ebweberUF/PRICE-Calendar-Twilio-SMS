"""Mosio SMS API client for sending reminders and polling replies."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Any

import requests

log = logging.getLogger(__name__)


@dataclass
class SendResult:
    """Result from sending an SMS."""

    success: bool
    transaction_id: str
    error_code: int
    error_message: str


@dataclass
class InboundMessage:
    """An inbound SMS from a participant."""

    message_id: int
    phone: str
    body: str
    date: str
    direction: str


class MosioClient:
    """Client for the Mosio REST API."""

    def __init__(self, api_key: str, base_url: str, from_number: str = "") -> None:
        self.base_url = base_url.rstrip("/")
        self.from_number = from_number
        self.session = requests.Session()
        self.session.headers.update({
            "X-ApiKey": api_key,
            "Content-Type": "application/x-www-form-urlencoded",
        })

    def send_sms(self, phone: str, message: str) -> SendResult:
        """Send a single SMS message.

        POST /send_single_sms
        Params: Phone (11-digit), Message (160 char max), FromNumber (optional)
        """
        phone = normalize_phone(phone)
        data: dict[str, str] = {"Phone": phone, "Message": message}
        if self.from_number:
            data["FromNumber"] = self.from_number

        if len(message) > 160:
            log.warning("Message exceeds 160 chars (%d), will be multi-segment", len(message))

        try:
            resp = self.session.post(
                f"{self.base_url}/send_single_sms", data=data, timeout=30
            )
            resp.raise_for_status()
            body: dict[str, Any] = resp.json()
        except requests.RequestException:
            log.exception("Failed to send SMS to %s...%s", phone[:5], phone[-2:])
            return SendResult(
                success=False, transaction_id="", error_code=-1, error_message="Network error"
            )

        result = SendResult(
            success=body.get("Success", False),
            transaction_id=str(body.get("TransactionId", "")),
            error_code=body.get("ErrorCode", -1),
            error_message=body.get("ErrorMessage", ""),
        )

        if result.success:
            log.info("SMS sent to %s...%s, txn=%s", phone[:5], phone[-2:], result.transaction_id)
        else:
            log.error(
                "SMS failed to %s...%s: [%d] %s",
                phone[:5], phone[-2:], result.error_code, result.error_message,
            )

        return result

    def get_text_history(
        self, since: str | None = None, limit: int = 1000
    ) -> list[InboundMessage]:
        """Poll for inbound messages.

        GET /text_history?Since=<datetime>&Limit=<n>
        Returns messages where Direction == 'in'.

        Note: Content-Type must be cleared for GET requests — the GALLOP
        integration showed that Mosio rejects GET with form-urlencoded.
        """
        params: dict[str, str | int] = {"Limit": limit}
        if since:
            params["Since"] = since

        try:
            resp = self.session.get(
                f"{self.base_url}/text_history",
                params=params,
                headers={"Content-Type": ""},  # override for GET
                timeout=30,
            )
            resp.raise_for_status()
            body: dict[str, Any] = resp.json()
        except requests.RequestException:
            log.exception("Failed to poll text_history")
            return []

        if not body.get("Success", False):
            log.error("text_history error: %s", body.get("Error", "unknown"))
            return []

        messages: list[InboundMessage] = []
        for item in body.get("Contacts", []):
            if item.get("Direction") != "in":
                continue
            messages.append(
                InboundMessage(
                    message_id=item.get("Id", 0),
                    phone=item.get("Phone", ""),
                    body=item.get("Body", ""),
                    date=item.get("Date", ""),
                    direction="in",
                )
            )

        log.info("Polled %d inbound messages since %s", len(messages), since or "all")
        return messages

    def check_connection(self) -> tuple[bool, str]:
        """Verify Mosio API connectivity and key validity.

        Returns (success, error_message).
        """
        try:
            resp = self.session.get(
                f"{self.base_url}/text_history",
                params={"Limit": 1},
                headers={"Content-Type": ""},
                timeout=15,
            )
            resp.raise_for_status()
            body: dict[str, Any] = resp.json()
        except requests.RequestException as e:
            return False, f"Network error: {e}"

        if body.get("Success", False):
            return True, ""
        return False, body.get("ErrorMessage", "Unknown error")

    def carrier_lookup(self, phone: str) -> bool:
        """Check if a phone number is SMS-capable.

        POST /carrier_lookup
        Returns IsSmsEnabled bool.
        """
        phone = normalize_phone(phone)
        try:
            resp = self.session.post(
                f"{self.base_url}/carrier_lookup",
                data={"Phone": phone},
                timeout=30,
            )
            resp.raise_for_status()
            body: dict[str, Any] = resp.json()
        except requests.RequestException:
            log.exception("Carrier lookup failed for %s...%s", phone[:5], phone[-2:])
            return False

        enabled = body.get("IsSmsEnabled", False)
        if not enabled:
            log.warning(
                "Phone %s...%s not SMS-capable: %s",
                phone[:5], phone[-2:], body.get("ErrorMessage", ""),
            )
        return bool(enabled)


def normalize_phone(raw: str) -> str:
    """Normalize a phone number to 11-digit format (1XXXXXXXXXX)."""
    digits = re.sub(r"\D", "", raw)
    if len(digits) == 10:
        digits = "1" + digits
    if len(digits) != 11 or not digits.startswith("1"):
        log.warning("Unusual phone format: %s -> %s", raw, digits)
    return digits


def parse_response(body: str) -> str:
    """Parse a participant's SMS reply into a response status.

    Returns: 'confirmed', 'reschedule', 'cancel', or 'unknown'.
    """
    text = body.strip().upper()

    if text in ("1", "YES", "CONFIRM", "CONFIRMED", "Y"):
        return "confirmed"
    if text in ("2", "RESCHEDULE", "RESCHED"):
        return "reschedule"
    if text in ("3", "CANCEL", "NO", "N"):
        return "cancel"

    return "unknown"
