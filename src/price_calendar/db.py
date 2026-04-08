"""SQLite state tracking for SMS reminders. No PHI stored."""

from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any

_SCHEMA = """
CREATE TABLE IF NOT EXISTS reminders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    sharepoint_event_id TEXT NOT NULL,
    subject_id TEXT NOT NULL,
    study_code TEXT NOT NULL,
    phone_hash TEXT NOT NULL,
    mosio_transaction_id TEXT,
    sp_item_id INTEGER,
    reminder_type TEXT NOT NULL,
    sent_at TEXT NOT NULL,
    event_start TEXT NOT NULL,
    visit_name TEXT,
    location TEXT,
    experimenter_email TEXT NOT NULL,
    response_status TEXT DEFAULT 'pending',
    response_text TEXT,
    response_at TEXT,
    experimenter_notified INTEGER DEFAULT 0,
    created_at TEXT DEFAULT (datetime('now')),
    UNIQUE(sharepoint_event_id, reminder_type)
);

CREATE INDEX IF NOT EXISTS idx_reminders_pending
    ON reminders(response_status) WHERE response_status = 'pending';
CREATE INDEX IF NOT EXISTS idx_reminders_phone_hash
    ON reminders(phone_hash);
CREATE INDEX IF NOT EXISTS idx_reminders_event
    ON reminders(sharepoint_event_id);

CREATE TABLE IF NOT EXISTS poll_state (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""


class ReminderStore:
    """SQLite-backed store for reminder state tracking."""

    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(db_path))
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA foreign_keys=ON")
        self.conn.executescript(_SCHEMA)
        self.conn.commit()

    def close(self) -> None:
        self.conn.close()

    # -- Reminder CRUD --

    def has_reminder(self, sharepoint_event_id: str, reminder_type: str) -> bool:
        """Check if a reminder was already sent for this event + type."""
        row = self.conn.execute(
            "SELECT 1 FROM reminders WHERE sharepoint_event_id = ? AND reminder_type = ?",
            (sharepoint_event_id, reminder_type),
        ).fetchone()
        return row is not None

    def event_has_response(self, sharepoint_event_id: str) -> bool:
        """Check if any reminder for this event already received a response."""
        row = self.conn.execute(
            "SELECT 1 FROM reminders WHERE sharepoint_event_id = ? "
            "AND response_status NOT IN ('pending', 'no_response')",
            (sharepoint_event_id,),
        ).fetchone()
        return row is not None

    def insert_reminder(
        self,
        sharepoint_event_id: str,
        subject_id: str,
        study_code: str,
        phone_hash: str,
        mosio_transaction_id: str | None,
        reminder_type: str,
        event_start: str,
        visit_name: str,
        location: str,
        experimenter_email: str,
        sp_item_id: int | None = None,
    ) -> int:
        """Insert a new reminder record. Returns the row id."""
        cur = self.conn.execute(
            """INSERT INTO reminders
            (sharepoint_event_id, subject_id, study_code, phone_hash,
             mosio_transaction_id, sp_item_id, reminder_type, sent_at, event_start,
             visit_name, location, experimenter_email)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                sharepoint_event_id,
                subject_id,
                study_code,
                phone_hash,
                mosio_transaction_id,
                sp_item_id,
                reminder_type,
                datetime.utcnow().isoformat(),
                event_start,
                visit_name,
                location,
                experimenter_email,
            ),
        )
        self.conn.commit()
        return cur.lastrowid  # type: ignore[return-value]

    def find_pending_by_phone_hash(self, phone_hash: str) -> dict[str, Any] | None:
        """Find the most recent pending reminder matching a phone hash."""
        row = self.conn.execute(
            """SELECT * FROM reminders
            WHERE phone_hash = ? AND response_status = 'pending'
            ORDER BY sent_at DESC LIMIT 1""",
            (phone_hash,),
        ).fetchone()
        return dict(row) if row else None

    def update_response(
        self, reminder_id: int, status: str, response_text: str
    ) -> None:
        """Update a reminder with the participant's response."""
        self.conn.execute(
            """UPDATE reminders
            SET response_status = ?, response_text = ?, response_at = ?
            WHERE id = ?""",
            (status, response_text, datetime.utcnow().isoformat(), reminder_id),
        )
        self.conn.commit()

    def mark_experimenter_notified(self, reminder_id: int) -> None:
        """Mark that the experimenter was notified of this response."""
        self.conn.execute(
            "UPDATE reminders SET experimenter_notified = 1 WHERE id = ?",
            (reminder_id,),
        )
        self.conn.commit()

    def get_unnotified_responses(self) -> list[dict[str, Any]]:
        """Get reminders with responses that haven't been sent to experimenters."""
        rows = self.conn.execute(
            """SELECT * FROM reminders
            WHERE response_status NOT IN ('pending', 'no_response')
            AND experimenter_notified = 0"""
        ).fetchall()
        return [dict(r) for r in rows]

    def get_expired_pending(self) -> list[dict[str, Any]]:
        """Get pending reminders whose event has already passed."""
        now = datetime.utcnow().isoformat()
        rows = self.conn.execute(
            """SELECT * FROM reminders
            WHERE response_status = 'pending' AND event_start < ?""",
            (now,),
        ).fetchall()
        return [dict(r) for r in rows]

    def mark_no_response(self, reminder_id: int) -> None:
        """Mark a reminder as no_response (event passed without reply)."""
        self.conn.execute(
            """UPDATE reminders
            SET response_status = 'no_response', response_at = ?
            WHERE id = ?""",
            (datetime.utcnow().isoformat(), reminder_id),
        )
        self.conn.commit()

    # -- Poll state --

    def get_last_poll_time(self) -> str | None:
        """Get the last time we polled Mosio for replies."""
        row = self.conn.execute(
            "SELECT value FROM poll_state WHERE key = 'last_poll'"
        ).fetchone()
        return row["value"] if row else None

    def set_last_poll_time(self, iso_time: str) -> None:
        """Update the last poll timestamp."""
        self.conn.execute(
            "INSERT OR REPLACE INTO poll_state (key, value) VALUES ('last_poll', ?)",
            (iso_time,),
        )
        self.conn.commit()

    # -- Status counts --

    def get_status_counts(self) -> dict[str, int]:
        """Get counts of reminders by response_status."""
        rows = self.conn.execute(
            "SELECT response_status, COUNT(*) as cnt FROM reminders GROUP BY response_status"
        ).fetchall()
        return {r["response_status"]: r["cnt"] for r in rows}
