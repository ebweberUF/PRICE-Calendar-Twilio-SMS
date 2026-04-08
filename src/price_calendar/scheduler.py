"""Orchestrates the SMS reminder workflow in a single run.

Each run performs three phases:
1. Send reminders for upcoming events (writes to SharePoint SMS Reminder Log)
2. Poll Twilio for participant replies (updates SharePoint, triggers notification email)
3. Escalate no-response reminders after event passes

The Write flow handles notification emails inline — when update_response is
called with a non-pending status, it looks up the Lead Experimenter from the
calendar event and sends an email from price-ctsi@ufl.edu.
"""

from __future__ import annotations

import hashlib
import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from .calendar_client import CalendarEvent, get_upcoming_events
from .config import Config
from .twilio_client import TwilioClient, normalize_phone, parse_response
from .redcap_client import RedcapClient
from .sharepoint_store import SharePointStore

log = logging.getLogger(__name__)

# Reminder message templates (must stay <=160 chars, NO participant names — HIPAA)
_MSG_72H = (
    "PRICE Reminder: {visit} on {date} at {time}, {location}. "
    "Reply 1=Confirm 2=Reschedule 3=Cancel"
)
_MSG_24H = (
    "PRICE Reminder: {visit} is TOMORROW {date} at {time}, {location}. "
    "Reply 1=Confirm 2=Reschedule 3=Cancel"
)
_MSG_CLARIFY = (
    "Sorry, we didn't understand your reply. "
    "Please reply 1=Confirm 2=Reschedule 3=Cancel"
)


def run_cycle(config: Config, dry_run: bool = False) -> dict[str, Any]:
    """Execute one full send/poll/escalate cycle.

    Returns a summary dict with counts from each phase.
    """
    store = SharePointStore(config.pa_read_flow_url, config.pa_write_flow_url)
    twilio = TwilioClient(
        config.twilio_account_sid,
        config.twilio_auth_token,
        config.twilio_messaging_service_sid,
    )
    redcap = RedcapClient()

    send_summary = _phase_send(config, store, twilio, redcap, dry_run)
    poll_summary = _phase_poll(config, store, twilio, dry_run)
    escalate_summary = _phase_escalate(config, store, dry_run)

    summary: dict[str, Any] = {
        "send": send_summary,
        "poll": poll_summary,
        "escalate": escalate_summary,
    }
    log.info("Cycle complete: %s", summary)
    return summary


def _phase_send(
    config: Config,
    store: SharePointStore,
    twilio: TwilioClient,
    redcap: RedcapClient,
    dry_run: bool,
) -> dict[str, int]:
    """Phase 1: Send reminders for upcoming events."""
    log.info("=== Phase 1: Send Reminders ===")
    counts = {"sent_72h": 0, "sent_24h": 0, "skipped": 0, "failed": 0, "no_phone": 0}

    sms_flags = store.get_sms_flags()
    raw_items = store.get_upcoming_events(hours_ahead=73)
    events = get_upcoming_events(raw_items, sms_flags=sms_flags)

    for event in events:
        mapping = config.get_study_mapping(event.study_code)
        if not mapping:
            log.debug("No study mapping for %s, skipping", event.study_code)
            counts["skipped"] += 1
            continue

        # If participant already responded to any reminder for this event, skip
        if store.event_has_response(event.sharepoint_event_id):
            counts["skipped"] += 1
            continue

        # Determine which reminder to send
        reminder_type = _get_reminder_type(event)
        if not reminder_type:
            counts["skipped"] += 1
            continue

        # Skip if already sent this type
        if store.has_reminder(event.sharepoint_event_id, reminder_type):
            counts["skipped"] += 1
            continue

        # For 24h reminder: skip if 72h was sent AND got a response already
        # (but allow 24h to send even without a prior 72h — handles short-notice visits)
        if reminder_type == "24h" and store.has_reminder(
            event.sharepoint_event_id, "72h"
        ):
            # 72h exists — only send 24h if no response yet (as a follow-up)
            if store.event_has_response(event.sharepoint_event_id):
                counts["skipped"] += 1
                continue

        # Look up phone from REDCap (in memory only)
        phone = redcap.get_phone_number(mapping, event.subject_id)
        if not phone:
            counts["no_phone"] += 1
            continue

        phone_normalized = normalize_phone(phone)
        phone_hash = hashlib.sha256(phone_normalized.encode()).hexdigest()

        # Format message
        msg = _format_reminder(event, reminder_type)

        if dry_run:
            log.info("[DRY RUN] Would send %s reminder to %s", reminder_type, event.subject_id)
            counts[f"sent_{reminder_type}"] += 1
            continue

        # Send via Twilio
        result = twilio.send_sms(phone_normalized, msg)
        if not result.success:
            counts["failed"] += 1
            continue

        # Log to SharePoint SMS Reminder Log
        store.log_reminder(
            calendar_event_id=event.sharepoint_event_id,
            subject_id=event.subject_id,
            study_code=event.study_code,
            visit_name=event.visit,
            event_start=event.event_start,
            location=event.location,
            experimenter_email=event.organizer_email,
            reminder_type=reminder_type,
            message_sid=result.message_sid,
            phone_hash=phone_hash,
        )
        counts[f"sent_{reminder_type}"] += 1

    log.info("Send phase: %s", counts)
    return counts


def _phase_poll(
    config: Config,
    store: SharePointStore,
    twilio: TwilioClient,
    dry_run: bool,
) -> dict[str, int]:
    """Phase 2: Poll Twilio for inbound replies and process them."""
    log.info("=== Phase 2: Poll Responses ===")
    counts = {"confirmed": 0, "reschedule": 0, "cancel": 0, "unknown": 0, "no_match": 0}

    # Poll last 2 hours of inbound messages from Twilio
    # SharePoint dedup prevents double-processing (only pending items match)
    two_hours_ago = datetime.now(timezone.utc) - timedelta(hours=2)
    messages = twilio.get_inbound_messages(since=two_hours_ago)

    for msg in messages:
        phone_hash = hashlib.sha256(normalize_phone(msg["from"]).encode()).hexdigest()
        reminder = store.find_pending_by_phone_hash(phone_hash)

        if not reminder:
            counts["no_match"] += 1
            continue

        status = parse_response(msg["body"])

        if status == "unknown":
            counts["unknown"] += 1
            if not dry_run:
                twilio.send_sms(normalize_phone(msg["from"]), _MSG_CLARIFY)
            continue

        counts[status] += 1

        if dry_run:
            log.info(
                "[DRY RUN] Would update %s to %s", reminder["subject_id"], status
            )
            continue

        # Update SharePoint — Write flow also sends notification email
        store.update_response(
            sp_item_id=reminder["sp_item_id"],
            response_status=status,
            response_text=msg["body"],
        )

    log.info("Poll phase: %s", counts)
    return counts


def _phase_escalate(
    config: Config,
    store: SharePointStore,
    dry_run: bool,
) -> dict[str, int]:
    """Phase 3: Mark expired pending reminders as no_response."""
    log.info("=== Phase 3: Escalate No-Response ===")
    counts = {"escalated": 0}

    expired = store.get_expired_pending()
    for reminder in expired:
        if dry_run:
            log.info("[DRY RUN] Would escalate %s", reminder["subject_id"])
            counts["escalated"] += 1
            continue

        # Update SharePoint — Write flow also sends notification email
        store.update_response(
            sp_item_id=reminder["sp_item_id"],
            response_status="no_response",
            response_text="",
        )
        counts["escalated"] += 1

    log.info("Escalate phase: %s", counts)
    return counts


def _get_reminder_type(event: CalendarEvent) -> str | None:
    """Determine which reminder type to send based on time until event.

    Timing windows:
    - 36-73h out  -> "72h" reminder
    - 4-36h out   -> "24h" reminder
    - <4h out     -> too late, skip
    """
    try:
        event_dt = datetime.fromisoformat(event.event_start.replace("Z", "+00:00"))
    except ValueError:
        log.warning("Cannot parse event_start: %s", event.event_start)
        return None

    now = datetime.now(timezone.utc)
    hours_until = (event_dt - now).total_seconds() / 3600

    if hours_until < 4:
        return None  # too late
    if hours_until >= 36:
        return "72h"
    # 4-36h out: send 24h reminder
    return "24h"


def _format_reminder(event: CalendarEvent, reminder_type: str) -> str:
    """Format a reminder message from event data. No participant names — HIPAA."""
    try:
        event_dt = datetime.fromisoformat(event.event_start.replace("Z", "+00:00"))
        date_str = event_dt.strftime("%m/%d/%Y")
        time_str = event_dt.strftime("%I:%M %p")
    except ValueError:
        date_str = event.event_start[:10]
        time_str = ""

    visit = event.visit or "Study Visit"
    location = event.location or "PRICE Center"

    template = _MSG_24H if reminder_type == "24h" else _MSG_72H
    msg = template.format(visit=visit, date=date_str, time=time_str, location=location)

    # Truncate if over 160 chars
    if len(msg) > 160:
        msg = msg[:157] + "..."

    return msg
