# Mosio SMS Calendar Handoff

## Purpose

This document is a restart guide for the PRICE Calendar SMS reminder service so development can be picked up on another computer without reconstructing the architecture from scratch.

It covers:

- what is already implemented
- how the current Mosio SMS workflow is supposed to work
- which files matter
- which secrets and local dependencies are required on a new machine
- what is still incomplete or risky
- the most sensible next steps

This write-up is based on direct inspection of the current repository state on 2026-04-08. No end-to-end runtime validation was performed during this handoff session.

## Executive Summary

The repository already contains a functioning first-pass implementation of a standalone Python service that:

1. fetches upcoming PRICE calendar events
2. checks SharePoint to see which events have SMS reminders enabled
3. looks up participant phone numbers from REDCap on demand
4. sends SMS reminders through Mosio
5. stores local state in SQLite Check this part, !!!!!i don't want any local dependencies
6. polls Mosio for participant replies
7. writes reminder status updates to a SharePoint list so Power Automate can notify the lead experimenter

The codebase is materially beyond the planning stage. Core modules exist for configuration, calendar fetch, REDCap lookup, Mosio send/poll, SharePoint logging, SQLite state tracking, and CLI entry points.

What is not done is the operational hardening:

- there are no tests
- there is no `.env.example`
- there are still stray credential files in the repo/workspace context
- at least one config-health check is overly optimistic and can report success on failure
- production setup on a new computer still depends on external token files and service-side configuration that are not created automatically by this repo

## Repository Snapshot

Relevant top-level files and directories:

- `environment.yml` - conda environment definition
- `pyproject.toml` - package metadata and dev tool config
- `config/study_mappings.yaml` - studyCode to REDCap field mapping
- `src/price_calendar/` - application code
- `tests/` - exists but currently empty
- `test_api.py` - ad hoc Mosio connectivity test script
- `mosio.txt` - local credential/reference file; should be treated as sensitive and not as application configuration

## What Has Already Been Built

### 1. CLI application shell

The package is installable as `price-calendar` and runnable as:

- `python -m price_calendar run`
- `python -m price_calendar send-test <phone>`
- `python -m price_calendar check-config`
- `python -m price_calendar status`

Implemented in:

- `src/price_calendar/main.py`
- `src/price_calendar/__main__.py`

### 2. Configuration loader

The app loads runtime configuration from:

- workspace `.env`
- `config/study_mappings.yaml`

The code expects these environment variables:

- `MOSIO_API_KEY`
- `MOSIO_BASE_URL` with default `https://api.mosio.com/api`
- `MOSIO_FROM_NUMBER`
- `CALENDAR_API_URL`
- `REDCAP_PROJECTS_PATH` with default `~/.claude/redcap/projects.json`
- `SHAREPOINT_TOKEN_PATH` with default `~/.sharepoint/token.json`
- `DB_PATH` with default `~/.price-calendar/reminders.db`
- `TEAM_EMAILS`

Implemented in:

- `src/price_calendar/config.py`

### 3. Calendar event intake

The service pulls events from the PRICE calendar API, then cross-checks SharePoint directly to see whether the `SMS Reminder` checkbox is enabled.

The event filter logic currently excludes:

- cancelled visits
- confidential visits
- visits without a `subjectId`
- visits not opted in for SMS in SharePoint

Implemented in:

- `src/price_calendar/calendar_client.py`

### 4. REDCap phone lookup

Phone numbers are not stored permanently by design. The app loads project API tokens from the REDCap projects vault and fetches the participant phone field on demand using the study mapping.

Implemented in:

- `src/price_calendar/redcap_client.py`
- `config/study_mappings.yaml`

### 5. Mosio API integration

There is already a reusable Mosio client with methods for:

- sending a single SMS
- polling text history for inbound replies
- carrier lookup
- phone normalization
- parsing response text into workflow statuses

Supported response parsing:

- `1`, `YES`, `CONFIRM`, `CONFIRMED`, `Y` -> `confirmed`
- `2`, `RESCHEDULE`, `RESCHED` -> `reschedule`
- `3`, `CANCEL`, `NO`, `N` -> `cancel`
- anything else -> `unknown`

Implemented in:

- `src/price_calendar/mosio_client.py`

### 6. Reminder orchestration

The main business logic is implemented as a three-phase cycle:

1. send reminders
2. poll responses
3. escalate no-response events

Implemented in:

- `src/price_calendar/scheduler.py`

### 7. Local SQLite state store

The service maintains local state in SQLite with WAL mode enabled.

The `reminders` table stores:

- SharePoint event ID
- subject ID
- study code
- hashed phone number
- Mosio transaction ID
- SharePoint log item ID
- reminder type (`72h` or `24h`)
- send timestamp
- event metadata
- experimenter email
- response status/text/timestamp
- notification flag

The `poll_state` table stores the last Mosio poll timestamp.

Implemented in:

- `src/price_calendar/db.py`

### 8. SharePoint logging for downstream notifications

The system writes to a SharePoint list named `SMS Reminder Log`.

That list is the handoff point to Power Automate. The intended pattern is:

- Python service creates a reminder log item when an SMS is sent
- Python service updates the same item when a reply is received or when the reminder expires without reply
- Power Automate watches `ResponseStatus` changes and emails the lead experimenter

Implemented in:

- `src/price_calendar/notifier.py`

### 9. Packaging and dev tooling skeleton

The repo already includes:

- Python 3.11 environment setup through conda
- editable install through pip in `environment.yml`
- Ruff config
- mypy strict config
- pytest config

Defined in:

- `environment.yml`
- `pyproject.toml`

## Current Runtime Architecture

### High-level flow

```text
PRICE calendar API
    -> candidate upcoming events

SharePoint PRICECalendar list
    -> SMS opt-in flag per event

study_mappings.yaml
    -> studyCode -> REDCap project + phone field mapping

REDCap API
    -> phone number lookup for subject

Mosio API
    -> send outbound reminder
    -> poll inbound reply history

SQLite local store
    -> dedupe reminders
    -> remember pending reminders
    -> track last poll timestamp

SharePoint SMS Reminder Log
    -> record pending/confirmed/reschedule/cancel/no_response

Power Automate
    -> email lead experimenter on SharePoint status change
```

### Phase 1: Send reminders

Implemented in `scheduler._phase_send`.

Flow:

1. Fetch events in the next 73 hours from the calendar API.
2. Query SharePoint for the SMS opt-in flag.
3. Drop events that do not have a study mapping.
4. Drop events that already have a non-pending response.
5. Determine reminder type:
   - `72h` when roughly 48 to 73 hours out
   - `24h` when roughly 23 to 36 hours out
6. Skip duplicate reminders already stored in SQLite.
7. For `24h`, only send if the `72h` reminder already exists and there was no response.
8. Look up the participant phone number from REDCap.
9. Normalize the phone number to `1XXXXXXXXXX`.
10. Hash the normalized phone for local matching.
11. Format a short HIPAA-conscious message with no participant name.
12. Send via Mosio.
13. Log the reminder to the SharePoint `SMS Reminder Log` list.
14. Persist the reminder locally in SQLite.

### Phase 2: Poll responses

Implemented in `scheduler._phase_poll`.

Flow:

1. Read the last poll timestamp from SQLite.
2. If none exists, default to two hours ago.
3. Call Mosio `text_history`.
4. Ignore any inbound message whose phone hash does not match a pending reminder.
5. Parse the response body into one of:
   - `confirmed`
   - `reschedule`
   - `cancel`
   - `unknown`
6. If unknown, send a clarification SMS and leave the reminder pending.
7. If recognized:
   - update local SQLite response fields
   - update the SharePoint reminder log item
   - mark the experimenter as notified locally
8. Save the new poll timestamp.

### Phase 3: Escalate no-response reminders

Implemented in `scheduler._phase_escalate`.

Flow:

1. Query SQLite for pending reminders whose event time has passed.
2. Mark them as `no_response` locally.
3. Update the SharePoint reminder log item to `no_response`.
4. Rely on Power Automate to notify the lead experimenter.

## Message Design

There are currently three SMS templates in code:

- 72-hour reminder
- 24-hour reminder
- clarification message for unrecognized replies

Constraints enforced in the code:

- no participant name in the SMS body
- target length of 160 characters
- truncation if the message exceeds 160 characters

Current response protocol sent to participants:

- `1 = Confirm`
- `2 = Reschedule`
- `3 = Cancel`

## Important Files and Their Roles

### Application code

- `src/price_calendar/main.py`
  - CLI entry points
  - logging setup
  - `run`, `send-test`, `check-config`, `status`

- `src/price_calendar/config.py`
  - environment loading
  - study mapping loading

- `src/price_calendar/scheduler.py`
  - main orchestration logic
  - reminder timing and workflow rules

- `src/price_calendar/mosio_client.py`
  - Mosio REST calls
  - phone normalization
  - response parsing

- `src/price_calendar/calendar_client.py`
  - calendar API fetch
  - SharePoint opt-in lookup

- `src/price_calendar/redcap_client.py`
  - REDCap token loading
  - participant phone lookup

- `src/price_calendar/notifier.py`
  - SharePoint `SMS Reminder Log` create/update operations

- `src/price_calendar/db.py`
  - SQLite schema and state management

### Configuration files

- `config/study_mappings.yaml`
  - currently only contains one study mapping: `ULLTRA`

- `.env`
  - local runtime secrets and endpoints
  - should exist locally but should not be copied into documentation with real values

### Ad hoc/local-only files that need cleanup or caution

- `test_api.py`
  - contains a hard-coded Mosio API key
  - should be treated as sensitive
  - likely used to mimic a known-working GALLOP Mosio integration pattern

- `mosio.txt`
  - appears to contain Mosio-related credentials or references
  - should be treated as sensitive
  - should not be the long-term configuration mechanism

## External Dependencies Required on Another Computer

To continue development on another machine, the code alone is not enough. You also need the local runtime dependencies below.

### 1. Python environment

Expected stack:

- conda
- Python 3.11
- editable install of this package with dev dependencies

### 2. Mosio access

Required:

- valid Mosio API key
- correct Mosio base URL
- optional but likely useful `FromNumber`

Important:

- do not rely on `mosio.txt` as the stable config source
- the app itself loads Mosio configuration from `.env`

### 3. PRICE calendar API access

Required:

- a valid `CALENDAR_API_URL`

The code expects an `/events` endpoint that accepts:

- `startDate`
- `endDate`

### 4. REDCap token vault

Required local file:

- `~/.claude/redcap/projects.json` by default

The code expects a structure like:

- project alias
- API URL
- API token

This must include every project alias referenced by `config/study_mappings.yaml`.

### 5. SharePoint token file

Required local file:

- `~/.sharepoint/token.json` by default

The code expects that file to contain either:

- `access_token`
- or `token`

This token is used for:

- reading the SMS opt-in checkbox from the `PRICECalendar` list
- creating and updating items in the `SMS Reminder Log` list

### 6. SharePoint list dependencies

The following SharePoint lists must exist and be reachable with the token:

- `PRICECalendar`
- `SMS Reminder Log`

Expected fields in `SMS Reminder Log` based on the code:

- `Title`
- `SubjectID`
- `StudyCode`
- `VisitName`
- `EventStart`
- `Location`
- `ExperimenterEmail`
- `ReminderType`
- `ResponseStatus`
- `MosioTransactionID`
- `CalendarEventID`
- `ResponseText`
- `ResponseAt`

The expected SharePoint list item type is hard-coded as:

- `SP.Data.SMS_x0020_Reminder_x0020_LogListItem`

If the list internal name differs, SharePoint writes will fail.

### 7. Power Automate flow

This repo does not send emails directly. It assumes a Power Automate flow already exists that watches the `SMS Reminder Log` list and emails the lead experimenter when `ResponseStatus` changes.

That flow is an external system dependency and must either:

- already exist in the target environment
- or be rebuilt/exported/imported separately

## Setup on Another Computer

These are the practical steps to resume work on a second machine.

### 1. Clone the repository

Clone the repo to the new machine.

### 2. Create the conda environment

Run:

```bash
conda env create -f environment.yml
conda activate price-calendar
```

Because `environment.yml` installs `-e ".[dev]"`, the package should be available in editable mode after the environment is created.

### 3. Recreate the `.env` file locally

Populate `.env` with the required variables, but do not copy real secrets into source control.

Minimum required values:

- `MOSIO_API_KEY`
- `CALENDAR_API_URL`

Strongly expected values:

- `MOSIO_BASE_URL`
- `MOSIO_FROM_NUMBER`
- `REDCAP_PROJECTS_PATH`
- `SHAREPOINT_TOKEN_PATH`
- `DB_PATH`
- `TEAM_EMAILS`

### 4. Recreate or copy the REDCap token vault

Ensure the file pointed to by `REDCAP_PROJECTS_PATH` exists and contains all needed project aliases.

### 5. Recreate or copy the SharePoint token file

Ensure the file pointed to by `SHAREPOINT_TOKEN_PATH` exists and contains a currently valid token.

This repo does not currently automate SharePoint token acquisition.

### 6. Verify study mappings

Open `config/study_mappings.yaml` and confirm the study codes you need are present.

Right now the repo only includes:

- `ULLTRA`

If more studies should receive reminders, their REDCap alias and phone field mappings need to be added.

### 7. Run config validation

Run:

```bash
python -m price_calendar check-config
```

Important caveat: the current implementation of `check-config` is not fully trustworthy for Mosio connectivity because of a logic issue described later in this document.

### 8. Run a dry cycle

Run:

```bash
python -m price_calendar run --dry-run
```

This is the safest first validation because it exercises the main workflow without actually sending texts.

### 9. Send a live test SMS if appropriate

Run:

```bash
python -m price_calendar send-test 3525551234
```

Use a controlled test number.

### 10. Set up scheduled execution

The scheduler module is clearly intended to run every 15 minutes on a Windows host via Task Scheduler, but this repo does not currently include a Task Scheduler XML export or installer script.

You will need to create that scheduled task manually or script it.

## What Still Needs To Be Done

This is the most important section if the goal is to continue development instead of just understanding the current state.

### Highest priority

1. Remove or rotate exposed Mosio credentials.

   Evidence:

   - `test_api.py` contains a hard-coded API key
   - `mosio.txt` contains Mosio-related secrets or identifiers

   Action:

   - rotate any exposed key that is still valid
   - remove secrets from tracked files
   - move all runtime configuration into `.env` and local secret stores only

2. Validate the Mosio API behavior against the known-working pattern.

   Why this matters:

   - `test_api.py` appears to deliberately mimic a known-working GALLOP integration pattern
   - it overrides `Content-Type` for `GET /text_history`
   - it posts raw form data for `carrier_lookup`
   - the reusable `MosioClient` does not currently mirror those exact request details

   Action:

   - verify whether the current `MosioClient` works with the real production key
   - if not, update the client to match the proven request format

3. Fix the health check so Mosio failures are not reported as success.

   Current issue:

   - `main.cmd_check_config` treats `mosio.get_text_history(limit=1)` as successful if the return value is not `None`
   - `MosioClient.get_text_history` returns an empty list on failure, not `None`
   - result: Mosio connectivity can fail while `check-config` still prints `connected`

   Action:

   - make `get_text_history` return explicit success/failure metadata
   - or change `check-config` to detect request errors correctly

4. Add tests before making larger changes.

   Current state:

   - `tests/` exists but contains no test files

   Minimum useful test coverage:

   - phone normalization
   - response parsing
   - reminder type timing logic
   - reminder message formatting and truncation
   - SQLite dedupe and state transitions
   - scheduler behavior with mocked Mosio, REDCap, calendar, and SharePoint calls

5. Confirm all SharePoint field names and internal list names in the real tenant.

   Why this matters:

   - the code uses hard-coded list names and field names
   - SharePoint internal names are easy to get wrong
   - list item type is hard-coded

   Action:

   - verify both `PRICECalendar` and `SMS Reminder Log`
   - confirm `SMS_x0020_Reminder`
   - confirm `SP.Data.SMS_x0020_Reminder_x0020_LogListItem`

### Medium priority

6. Create `.env.example` and setup documentation.

   The new machine setup currently depends on reading source code to discover required environment variables.

7. Export or document the Power Automate flow.

   The code assumes this flow exists, but the repo does not preserve its logic.

8. Script the Windows Task Scheduler installation.

   The scheduler cadence is implied in comments but not operationalized in the repo.

9. Expand `study_mappings.yaml` for all studies that should participate.

10. Decide whether carrier lookup should be used before sends.

   The code implements `carrier_lookup` in the Mosio client, but does not use it in the send path.

### Lower priority hardening

11. Add retry/backoff and alerting for transient failures.

   Current code logs failures but does not retry or escalate infrastructure problems.

12. Improve observability.

   Useful additions:

   - structured run summaries
   - explicit counts of SharePoint failures
   - alerting on repeated Mosio/REDCap/SharePoint failures

13. Reconcile stale comments and docs.

   Example:

   - `check-config` mentions Outlook token validation, but the current design routes notifications through SharePoint plus Power Automate instead of direct Outlook sending.

## Known Code-Level Risks and Issues

These are concrete issues identified from code inspection.

### 1. Credential exposure risk

The workspace currently includes files that appear to contain live or recently live Mosio credentials. This is the first thing to clean up before doing anything else on another machine.

### 2. `check-config` can falsely report Mosio success

As described above, the health check logic does not distinguish between an empty list caused by a successful call and an empty list caused by an exception path in `MosioClient.get_text_history`.

### 3. Notification success is not strictly verified before local notification state is set

In the response polling flow, the code calls `store.mark_experimenter_notified(...)` after attempting the SharePoint update. It does not first confirm that the SharePoint update actually succeeded.

Impact:

- a failed SharePoint update could cause the local DB to say the experimenter was notified even when the Power Automate trigger never happened

### 4. Mosio polling timestamp format should be verified

`test_api.py` uses a `Since` format like `2026-04-01T06:00:00Z`, while the scheduler stores and reuses timestamps formatted like `YYYY-MM-DD HH:MM:SS`.

This may work, but it should be explicitly verified with the real Mosio API.

### 5. No tests exist yet

Any refactor or bug fix is currently high-risk because there is no automated safety net.

### 6. New-computer bootstrap is only partially encoded in the repo

The repo knows how to load secrets and token paths, but it does not know how to generate those secrets, obtain those tokens, or recreate external automation dependencies.

## Data Handling Notes

The intended design is privacy-conscious:

- phone numbers are fetched from REDCap on demand
- the local SQLite DB stores a hash of the phone number instead of the raw phone
- SMS bodies avoid participant names

However, be aware of these practical realities:

- `subject_id` is stored locally
- free-text participant replies are stored in SQLite and SharePoint as `response_text`
- participants can send unexpected content, including potentially sensitive information

That means the system should still be treated as handling sensitive operational data even if it avoids storing raw phone numbers.

## Recommended Immediate Next Steps

If development is resuming on another machine, this is the sequence I would follow.

1. Rotate/remove any exposed Mosio credentials and stop using local text files for secret storage.
2. Recreate `.env`, REDCap vault access, and SharePoint token access on the new machine.
3. Run `python -m price_calendar run --dry-run` and confirm the calendar, SharePoint, and REDCap integrations all work.
4. Verify live Mosio behavior with a controlled test number.
5. Fix the `check-config` false positive and the notification-success tracking issue.
6. Add automated tests around the scheduler and Mosio parsing before further feature work.
7. Document or export the Power Automate flow and scheduled-task setup so the system is portable.

## Suggested Future Documentation To Add

This handoff file is enough to resume work, but the repo would be in much better shape with these follow-up docs:

- `.env.example`
- `docs/operations.md` or equivalent for day-to-day running
- `docs/sharepoint-fields.md` with verified internal names
- `docs/power-automate-flow.md` with the trigger and action logic
- `docs/new-machine-setup.md` with exact token/bootstrap steps

## Bottom Line

The project is already a real implementation, not a stub. The core Mosio SMS workflow exists and is coherent. The work remaining is mostly operational hardening, validation against live systems, test coverage, and cleanup of secret-management and deployment details so it can be safely and repeatably moved to another computer.