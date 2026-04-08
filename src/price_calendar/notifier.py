"""Write reminder status to the SharePoint SMS Reminder Log list.

Power Automate watches this list for ResponseStatus changes
and sends email notifications to the lead experimenter.
No Outlook token needed — Power Automate handles email natively.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests

log = logging.getLogger(__name__)

_SP_SITE_URL = "https://uflorida.sharepoint.com/sites/PRICE"
_SP_LIST_NAME = "SMS Reminder Log"


def log_reminder_to_sharepoint(
    token_path: Path,
    calendar_event_id: str,
    subject_id: str,
    study_code: str,
    visit_name: str,
    event_start: str,
    location: str,
    experimenter_email: str,
    reminder_type: str,
    mosio_transaction_id: str,
) -> int | None:
    """Create a new item in the SMS Reminder Log when a reminder is sent.

    Returns the SharePoint item ID, or None on failure.
    """
    token = _load_sp_token(token_path)
    if not token:
        log.error("No SharePoint token, cannot log reminder")
        return None

    payload = {
        "__metadata": {"type": _get_list_item_type()},
        "Title": f"{subject_id} - {reminder_type} - {visit_name}",
        "SubjectID": subject_id,
        "StudyCode": study_code,
        "VisitName": visit_name or "Study Visit",
        "EventStart": event_start,
        "Location": location or "",
        "ExperimenterEmail": experimenter_email,
        "ReminderType": reminder_type,
        "ResponseStatus": "pending",
        "MosioTransactionID": mosio_transaction_id,
        "CalendarEventID": calendar_event_id,
    }

    return _create_list_item(token, payload)


def update_response_in_sharepoint(
    token_path: Path,
    sp_item_id: int,
    response_status: str,
    response_text: str,
) -> bool:
    """Update the ResponseStatus on an existing SMS Reminder Log item.

    Power Automate triggers on this change to email the experimenter.
    """
    token = _load_sp_token(token_path)
    if not token:
        log.error("No SharePoint token, cannot update response")
        return False

    now = datetime.now(timezone.utc).isoformat()
    payload = {
        "__metadata": {"type": _get_list_item_type()},
        "ResponseStatus": response_status,
        "ResponseText": response_text or "",
        "ResponseAt": now,
    }

    return _update_list_item(token, sp_item_id, payload)


def find_pending_log_item(
    token_path: Path,
    calendar_event_id: str,
) -> dict[str, Any] | None:
    """Find the most recent pending log item for a calendar event."""
    token = _load_sp_token(token_path)
    if not token:
        return None

    api_url = (
        f"{_SP_SITE_URL}/_api/web/lists/getbytitle('{_SP_LIST_NAME}')/items"
        f"?$filter=CalendarEventID eq '{calendar_event_id}' and ResponseStatus eq 'pending'"
        f"&$orderby=Created desc"
        f"&$top=1"
    )

    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json;odata=nometadata",
    }

    try:
        resp = requests.get(api_url, headers=headers, timeout=30)
        resp.raise_for_status()
        items = resp.json().get("value", [])
        return items[0] if items else None
    except requests.RequestException:
        log.exception("Failed to query SMS Reminder Log")
        return None


# -- Internal helpers --


def _create_list_item(token: str, payload: dict[str, Any]) -> int | None:
    """Create a new item in the SMS Reminder Log list."""
    api_url = f"{_SP_SITE_URL}/_api/web/lists/getbytitle('{_SP_LIST_NAME}')/items"

    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json;odata=verbose",
        "Content-Type": "application/json;odata=verbose",
    }

    try:
        resp = requests.post(api_url, headers=headers, json=payload, timeout=30)
        resp.raise_for_status()
        item_id = resp.json().get("d", {}).get("Id")
        log.info("Created SMS Reminder Log item %s", item_id)
        return item_id
    except requests.RequestException:
        log.exception("Failed to create SMS Reminder Log item")
        return None


def _update_list_item(token: str, item_id: int, payload: dict[str, Any]) -> bool:
    """Update an existing item in the SMS Reminder Log list."""
    api_url = (
        f"{_SP_SITE_URL}/_api/web/lists/getbytitle('{_SP_LIST_NAME}')/items({item_id})"
    )

    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json;odata=verbose",
        "Content-Type": "application/json;odata=verbose",
        "IF-MATCH": "*",
        "X-HTTP-Method": "MERGE",
    }

    try:
        resp = requests.post(api_url, headers=headers, json=payload, timeout=30)
        resp.raise_for_status()
        log.info("Updated SMS Reminder Log item %d -> %s", item_id, payload.get("ResponseStatus"))
        return True
    except requests.RequestException:
        log.exception("Failed to update SMS Reminder Log item %d", item_id)
        return False


def _get_list_item_type() -> str:
    """Get the SharePoint list item type string."""
    # SP list item type follows: SP.Data.<InternalListName>ListItem
    return "SP.Data.SMS_x0020_Reminder_x0020_LogListItem"


def _load_sp_token(token_path: Path) -> str | None:
    """Load SharePoint Bearer token from the Playwright-captured token file."""
    if not token_path.exists():
        return None

    try:
        with open(token_path, encoding="utf-8") as f:
            data: dict[str, Any] = json.load(f)
        return data.get("access_token") or data.get("token")
    except (json.JSONDecodeError, KeyError):
        log.exception("Failed to parse SharePoint token from %s", token_path)
        return None
