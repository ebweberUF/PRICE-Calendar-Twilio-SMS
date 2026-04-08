"""Configuration loader for PRICE Calendar SMS reminders.

Core config (Twilio creds, PA flow URLs) comes from environment variables.
Study mappings and REDCap tokens come from SharePoint 'SMS Study Config' list
via the PA Read flow — no local files needed.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import requests
from dotenv import load_dotenv

log = logging.getLogger(__name__)


@dataclass
class StudyMapping:
    """Maps a calendar studyCode to its REDCap project and phone field."""

    study_code: str
    redcap_api_url: str
    redcap_api_token: str
    phone_field: str
    subject_id_field: str


@dataclass
class Config:
    """Application configuration."""

    twilio_account_sid: str
    twilio_auth_token: str
    twilio_messaging_service_sid: str
    calendar_api_url: str
    pa_read_flow_url: str
    pa_write_flow_url: str
    pa_reply_flow_url: str
    team_emails: list[str]
    study_mappings: dict[str, StudyMapping] = field(default_factory=dict)

    @classmethod
    def load(cls, env_path: Path | None = None) -> Config:
        """Load config from .env and SharePoint SMS Study Config list."""
        if env_path is None:
            env_path = Path(__file__).parent.parent.parent / ".env"
        load_dotenv(env_path)

        pa_read_url = _require_env("PA_READ_FLOW_URL")
        pa_write_url = _require_env("PA_WRITE_FLOW_URL")

        # Load study mappings from SharePoint via PA Read flow
        study_mappings = _load_study_config_from_sharepoint(pa_read_url)

        return cls(
            twilio_account_sid=_require_env("TWILIO_ACCOUNT_SID"),
            twilio_auth_token=_require_env("TWILIO_AUTH_TOKEN"),
            twilio_messaging_service_sid=_require_env("TWILIO_MESSAGING_SERVICE_SID"),
            calendar_api_url=_require_env("CALENDAR_API_URL"),
            pa_read_flow_url=pa_read_url,
            pa_write_flow_url=pa_write_url,
            pa_reply_flow_url=os.environ.get("PA_REPLY_FLOW_URL", ""),
            team_emails=os.environ.get("TEAM_EMAILS", "").split(","),
            study_mappings=study_mappings,
        )

    def get_study_mapping(self, study_code: str) -> StudyMapping | None:
        """Look up study mapping by calendar studyCode."""
        return self.study_mappings.get(study_code)


def _require_env(key: str) -> str:
    """Get a required environment variable or raise."""
    val = os.environ.get(key)
    if not val:
        raise ValueError(f"Missing required environment variable: {key}")
    return val


def _load_study_config_from_sharepoint(
    pa_read_url: str,
) -> dict[str, StudyMapping]:
    """Load study config from SharePoint SMS Study Config list via PA Read flow."""
    try:
        resp = requests.post(
            pa_read_url,
            json={"action": "get_study_config"},
            timeout=60,
        )
        resp.raise_for_status()
        items = resp.json().get("items", [])
    except requests.RequestException:
        log.exception("Failed to load study config from SharePoint")
        return {}

    mappings: dict[str, StudyMapping] = {}
    for item in items:
        active = item.get("Active", False)
        if not active:
            continue

        study_code = item.get("StudyCode", "")
        if not study_code:
            continue

        mappings[study_code] = StudyMapping(
            study_code=study_code,
            redcap_api_url=item.get("RedcapApiUrl", ""),
            redcap_api_token=item.get("RedcapApiToken", ""),
            phone_field=item.get("PhoneField", ""),
            subject_id_field=item.get("SubjectIdField", ""),
        )

    log.info("Loaded %d active study configs from SharePoint", len(mappings))
    return mappings
