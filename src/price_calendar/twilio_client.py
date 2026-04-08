"""Twilio SMS client for sending reminders and receiving replies.

Replaces mosio_client.py. Uses Twilio REST API directly (no SDK dependency).
Inbound replies are handled via webhook to Power Automate — no polling needed.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import requests

log = logging.getLogger(__name__)


@dataclass
class SendResult:
    """Result from sending an SMS."""

    success: bool
    message_sid: str
    error_code: int
    error_message: str


class TwilioClient:
    """Client for the Twilio REST API."""

    def __init__(
        self,
        account_sid: str,
        auth_token: str,
        messaging_service_sid: str,
    ) -> None:
        self.account_sid = account_sid
        self.auth_token = auth_token
        self.messaging_service_sid = messaging_service_sid
        self.base_url = (
            f"https://api.twilio.com/2010-04-01/Accounts/{account_sid}"
        )

    def send_sms(self, phone: str, message: str) -> SendResult:
        """Send a single SMS message via Twilio.

        Uses MessagingServiceSid for number management.
        Phone should be E.164 format (+1XXXXXXXXXX).
        """
        phone = normalize_phone(phone)

        if len(message) > 160:
            log.warning(
                "Message exceeds 160 chars (%d), Twilio will split into segments",
                len(message),
            )

        try:
            resp = requests.post(
                f"{self.base_url}/Messages.json",
                data={
                    "To": phone,
                    "MessagingServiceSid": self.messaging_service_sid,
                    "Body": message,
                },
                auth=(self.account_sid, self.auth_token),
                timeout=30,
            )
            body: dict[str, Any] = resp.json()
        except requests.RequestException:
            log.exception("Failed to send SMS to %s...%s", phone[:6], phone[-2:])
            return SendResult(
                success=False,
                message_sid="",
                error_code=-1,
                error_message="Network error",
            )

        if resp.status_code in (200, 201):
            sid = body.get("sid", "")
            log.info("SMS sent to %s...%s, sid=%s", phone[:6], phone[-2:], sid)
            return SendResult(
                success=True,
                message_sid=sid,
                error_code=0,
                error_message="",
            )

        error_code = body.get("code", resp.status_code)
        error_msg = body.get("message", body.get("error_message", "Unknown error"))
        log.error(
            "SMS failed to %s...%s: [%s] %s",
            phone[:6],
            phone[-2:],
            error_code,
            error_msg,
        )
        return SendResult(
            success=False,
            message_sid="",
            error_code=error_code,
            error_message=error_msg,
        )

    def get_inbound_messages(
        self, since: datetime | None = None
    ) -> list[dict[str, str]]:
        """Fetch inbound SMS messages from Twilio.

        Returns list of dicts with 'from', 'body', 'date', 'sid'.
        """

        params: dict[str, str | int] = {
            "To": self.messaging_service_sid,
            "PageSize": 100,
        }
        if since:
            params["DateSent>"] = since.strftime("%Y-%m-%d")

        try:
            resp = requests.get(
                f"{self.base_url}/Messages.json",
                params=params,
                auth=(self.account_sid, self.auth_token),
                timeout=30,
            )
            resp.raise_for_status()
            data = resp.json()
        except requests.RequestException:
            log.exception("Failed to fetch Twilio inbound messages")
            return []

        messages: list[dict[str, str]] = []
        for msg in data.get("messages", []):
            if msg.get("direction") != "inbound":
                continue
            messages.append({
                "from": msg.get("from", ""),
                "body": msg.get("body", ""),
                "date": msg.get("date_sent", ""),
                "sid": msg.get("sid", ""),
            })

        log.info("Polled %d inbound messages from Twilio", len(messages))
        return messages

    def check_connection(self) -> tuple[bool, str]:
        """Verify Twilio API connectivity and credentials."""
        try:
            resp = requests.get(
                f"{self.base_url}.json",
                auth=(self.account_sid, self.auth_token),
                timeout=15,
            )
            if resp.status_code == 200:
                return True, ""
            body = resp.json()
            return False, body.get("message", f"HTTP {resp.status_code}")
        except requests.RequestException as e:
            return False, f"Network error: {e}"


def normalize_phone(raw: str) -> str:
    """Normalize a phone number to E.164 format (+1XXXXXXXXXX)."""
    digits = re.sub(r"\D", "", raw)
    if len(digits) == 10:
        digits = "1" + digits
    if len(digits) != 11 or not digits.startswith("1"):
        log.warning("Unusual phone format: %s -> %s", raw, digits)
    return f"+{digits}"


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
