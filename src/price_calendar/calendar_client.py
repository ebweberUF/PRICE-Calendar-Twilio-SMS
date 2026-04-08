"""Fetch upcoming events from the PRICE calendar API.

SMS opt-in flags come from SharePointStore (via Power Automate),
not from direct SharePoint REST calls.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

import requests

log = logging.getLogger(__name__)


@dataclass
class CalendarEvent:
    """A calendar event with fields needed for SMS reminders."""

    sharepoint_event_id: str
    title: str
    event_start: str
    study_code: str
    organizer_name: str
    organizer_email: str
    subject_id: str
    visit: str
    location: str
    sms_opt_in: bool


def get_upcoming_events(
    base_url: str,
    sms_flags: dict[str, bool],
    hours_ahead: int = 73,
) -> list[CalendarEvent]:
    """Fetch upcoming events that have SMS Reminder opt-in enabled.

    Args:
        base_url: PRICE calendar API base URL.
        sms_flags: Dict mapping SharePoint event ID -> SMS opt-in bool,
                   obtained from SharePointStore.get_sms_flags().
        hours_ahead: How far ahead to look for events.

    Filters out:
    - Events with visitCancelled == true
    - Events with confidential == true
    - Events without a subjectId
    - Events where SMS Reminder is not checked
    """
    now = datetime.now(timezone.utc)
    end = now + timedelta(hours=hours_ahead)

    params = {
        "startDate": now.isoformat(),
        "endDate": end.isoformat(),
    }

    try:
        resp = requests.get(f"{base_url}/events", params=params, timeout=30)
        resp.raise_for_status()
        api_events: list[dict[str, Any]] = resp.json()
    except requests.RequestException:
        log.exception("Failed to fetch calendar events")
        return []

    if not api_events:
        return []

    events: list[CalendarEvent] = []
    for item in api_events:
        raw: dict[str, Any] = item.get("rawData") or {}

        if raw.get("visitCancelled"):
            continue
        if raw.get("confidential"):
            continue

        subject_id = raw.get("subjectId", "")
        if not subject_id:
            continue

        sp_id = str(item.get("sharepointEventId", ""))

        # Check SMS opt-in from flags
        if not sms_flags.get(sp_id, False):
            continue

        events.append(
            CalendarEvent(
                sharepoint_event_id=sp_id,
                title=item.get("title", ""),
                event_start=item.get("eventStart", ""),
                study_code=item.get("studyCode", ""),
                organizer_name=item.get("organizerName", ""),
                organizer_email=item.get("organizerEmail", ""),
                subject_id=subject_id,
                visit=raw.get("visit", ""),
                location=item.get("location", ""),
                sms_opt_in=True,
            )
        )

    log.info("Fetched %d SMS-eligible events in next %dh", len(events), hours_ahead)
    return events
