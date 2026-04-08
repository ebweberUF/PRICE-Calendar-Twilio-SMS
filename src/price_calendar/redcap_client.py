"""REDCap API client for on-demand phone number lookup. No PHI at rest."""

from __future__ import annotations

import logging
from typing import Any

import requests

from .config import StudyMapping

log = logging.getLogger(__name__)


class RedcapClient:
    """Looks up participant phone numbers from REDCap.

    Phone numbers are held in memory only and never written to disk.
    REDCap tokens come from the StudyMapping (loaded from SharePoint).
    """

    def get_phone_number(self, mapping: StudyMapping, subject_id: str) -> str | None:
        """Look up a participant's phone number from REDCap.

        Returns the phone string, or None if not found.
        Phone is held in memory only.
        """
        if not mapping.redcap_api_url or not mapping.redcap_api_token:
            log.error("No REDCap credentials for study: %s", mapping.study_code)
            return None

        try:
            resp = requests.post(
                mapping.redcap_api_url,
                data={
                    "token": mapping.redcap_api_token,
                    "content": "record",
                    "format": "json",
                    "type": "flat",
                    "records[0]": subject_id,
                    "fields[0]": mapping.phone_field,
                    "fields[1]": mapping.subject_id_field,
                },
                timeout=30,
            )
            resp.raise_for_status()
            records: list[dict[str, Any]] = resp.json()
        except requests.RequestException:
            log.exception(
                "REDCap lookup failed for %s in %s", subject_id, mapping.study_code
            )
            return None

        if not records:
            log.warning("No REDCap record found for %s", subject_id)
            return None

        phone = records[0].get(mapping.phone_field, "")
        if not phone:
            log.warning("No phone number for %s in field %s", subject_id, mapping.phone_field)
            return None

        log.info("Retrieved phone for %s (in memory only)", subject_id)
        return str(phone)
