"""Fetch upcoming events from the PRICE SharePoint calendar.

All data comes from the PRICECalendar SharePoint list via Power Automate.
No direct calendar API or SharePoint REST calls needed.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

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
    raw_items: list[dict[str, Any]],
    sms_flags: dict[str, bool],
) -> list[CalendarEvent]:
    """Parse SharePoint calendar items into CalendarEvents.

    Args:
        raw_items: Raw SharePoint items from store.get_upcoming_events().
        sms_flags: Dict mapping SharePoint event ID -> SMS opt-in bool,
                   obtained from SharePointStore.get_sms_flags().

    Filters out:
    - Events with visitCancelled == true
    - Events with confidential == true
    - Events without a subjectId
    - Events where SMS Reminder is not checked
    """
    if not raw_items:
        return []

    events: list[CalendarEvent] = []
    for item in raw_items:
        if item.get("visitCancelled"):
            continue
        if item.get("confidential"):
            continue

        subject_id = item.get("subjectId", "") or item.get("SubjectId", "")
        if not subject_id:
            continue

        sp_id = str(item.get("Id", item.get("ID", "")))

        # Check SMS opt-in from flags
        if not sms_flags.get(sp_id, False):
            continue

        events.append(
            CalendarEvent(
                sharepoint_event_id=sp_id,
                title=item.get("Title", ""),
                event_start=item.get("EventDate", ""),
                study_code=item.get("studyCode", "") or item.get("StudyCode", ""),
                organizer_name=item.get("organizerName", "") or item.get("OrganizerName", ""),
                organizer_email=item.get("organizerEmail", "") or item.get("OrganizerEmail", ""),
                subject_id=subject_id,
                visit=item.get("visit", "") or item.get("Visit", ""),
                location=item.get("Location", ""),
                sms_opt_in=True,
            )
        )

    log.info("Found %d SMS-eligible events from %d calendar items", len(events), len(raw_items))
    return events
