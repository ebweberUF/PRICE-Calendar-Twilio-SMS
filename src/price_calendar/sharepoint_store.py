"""SharePoint state store via Power Automate HTTP flows.

All SharePoint operations go through Power Automate — no direct
SharePoint auth needed.  Python just POSTs JSON to flow URLs.

PA flows return raw SharePoint items as {"items": [...]}.
All business logic parsing happens here in Python.
"""

from __future__ import annotations

import logging
from typing import Any

import requests

log = logging.getLogger(__name__)


class SharePointStore:
    """Reminder state operations via Power Automate flows."""

    def __init__(self, read_flow_url: str, write_flow_url: str) -> None:
        self.read_url = read_flow_url
        self.write_url = write_flow_url

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _read(self, payload: dict[str, Any]) -> list[dict[str, Any]]:
        """Call read flow, return items list (empty on failure)."""
        try:
            resp = requests.post(self.read_url, json=payload, timeout=60)
            resp.raise_for_status()
            data = resp.json()
            return data.get("items", [])
        except requests.RequestException:
            log.exception("PA read flow failed for action=%s", payload.get("action"))
            return []

    def _write(self, payload: dict[str, Any]) -> dict[str, Any] | None:
        """Call write flow, return response dict or None on failure."""
        try:
            resp = requests.post(self.write_url, json=payload, timeout=60)
            resp.raise_for_status()
            return resp.json()
        except requests.RequestException:
            log.exception("PA write flow failed for action=%s", payload.get("action"))
            return None

    # ------------------------------------------------------------------
    # SMS opt-in flags (from PRICECalendar list)
    # ------------------------------------------------------------------

    def get_sms_flags(self) -> dict[str, bool]:
        """Get SMS Reminder opt-in flags for upcoming calendar events."""
        items = self._read({"action": "get_sms_flags"})
        return {
            str(item.get("Id", "")): bool(item.get("SMS_x0020_Reminder", False))
            for item in items
        }

    def get_upcoming_events(self, hours_ahead: int = 73) -> list[dict[str, Any]]:
        """Get upcoming calendar events from SharePoint PRICECalendar list.

        Returns raw SharePoint items. Filtering (SMS opt-in, cancelled, etc.)
        is done in Python by calendar_client.
        """
        return self._read({
            "action": "get_upcoming_events",
            "hours_ahead": hours_ahead,
        })

    # ------------------------------------------------------------------
    # Deduplication
    # ------------------------------------------------------------------

    def has_reminder(self, calendar_event_id: str, reminder_type: str) -> bool:
        """Check if a reminder was already sent for this event + type."""
        items = self._read({
            "action": "has_reminder",
            "calendar_event_id": calendar_event_id,
            "reminder_type": reminder_type,
        })
        return len(items) > 0

    def event_has_response(self, calendar_event_id: str) -> bool:
        """Check if any reminder for this event already received a response."""
        items = self._read({
            "action": "event_has_response",
            "calendar_event_id": calendar_event_id,
        })
        return len(items) > 0

    # ------------------------------------------------------------------
    # Create reminder log item
    # ------------------------------------------------------------------

    def log_reminder(
        self,
        calendar_event_id: str,
        subject_id: str,
        study_code: str,
        visit_name: str,
        event_start: str,
        location: str,
        experimenter_email: str,
        reminder_type: str,
        message_sid: str,
        phone_hash: str,
    ) -> int | None:
        """Create a new item in the SMS Reminder Log.

        Returns the SharePoint item ID, or None on failure.
        """
        result = self._write({
            "action": "log_reminder",
            "calendar_event_id": calendar_event_id,
            "subject_id": subject_id,
            "study_code": study_code,
            "visit_name": visit_name,
            "event_start": event_start,
            "location": location,
            "experimenter_email": experimenter_email,
            "reminder_type": reminder_type,
            "message_sid": message_sid,
            "phone_hash": phone_hash,
        })
        if not result:
            return None
        item_id = result.get("item_id")
        if item_id:
            log.info("Created SMS Reminder Log item %s", item_id)
        return item_id

    # ------------------------------------------------------------------
    # Response matching
    # ------------------------------------------------------------------

    def find_pending_by_phone_hash(self, phone_hash: str) -> dict[str, Any] | None:
        """Find the most recent pending reminder matching a phone hash."""
        items = self._read({
            "action": "find_pending",
            "phone_hash": phone_hash,
        })
        if not items:
            return None
        item = items[0]
        return {
            "id": item.get("Id"),
            "subject_id": item.get("SubjectID", ""),
            "study_code": item.get("StudyCode", ""),
            "sp_item_id": item.get("Id"),
            "experimenter_email": item.get("ExperimenterEmail", ""),
        }

    # ------------------------------------------------------------------
    # Update response
    # ------------------------------------------------------------------

    def update_response(
        self,
        sp_item_id: int,
        response_status: str,
        response_text: str,
    ) -> bool:
        """Update ResponseStatus on an existing SMS Reminder Log item."""
        result = self._write({
            "action": "update_response",
            "item_id": sp_item_id,
            "response_status": response_status,
            "response_text": response_text,
        })
        if result and result.get("success"):
            log.info("Updated SMS Reminder Log item %d -> %s", sp_item_id, response_status)
            return True
        return False

    # ------------------------------------------------------------------
    # Escalation
    # ------------------------------------------------------------------

    def get_expired_pending(self) -> list[dict[str, Any]]:
        """Get pending reminders whose event has already passed."""
        items = self._read({"action": "get_expired_pending"})
        return [
            {
                "id": item.get("Id"),
                "sp_item_id": item.get("Id"),
                "subject_id": item.get("SubjectID", ""),
            }
            for item in items
        ]

    # ------------------------------------------------------------------
    # Status counts
    # ------------------------------------------------------------------

    def get_status_counts(self) -> dict[str, int]:
        """Get counts of reminders by ResponseStatus."""
        items = self._read({"action": "get_status_counts"})
        counts: dict[str, int] = {}
        for item in items:
            status = item.get("ResponseStatus", "unknown")
            counts[status] = counts.get(status, 0) + 1
        return counts
