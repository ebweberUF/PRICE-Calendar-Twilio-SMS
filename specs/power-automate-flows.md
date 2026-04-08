# Power Automate Flow Setup Guide

## Overview

Two flows replace all direct SharePoint API calls from Python.
Python POSTs JSON to the flow HTTP trigger URLs.
Power Automate handles SharePoint auth natively.

Flow definitions: `pa-flow-read.json` and `pa-flow-write.json`

## How to Import

### Option 1: Code View (recommended)

For each flow:

1. Go to **Power Automate** → **My flows** → **+ New flow** → **Instant cloud flow**
2. Name it (`PRICE SMS - Read` or `PRICE SMS - Write`)
3. Select **When an HTTP request is received** as trigger
4. Add **any** SharePoint action (e.g., "Get items") — this creates the SharePoint connection
5. Click the **Code View** button (top right, `</>` icon)
6. Replace the entire definition with the contents of the JSON file
7. Click **Save**
8. PA will prompt you to fix the SharePoint connection — select your existing connection to the PRICE site
9. Copy the **HTTP POST URL** from the trigger — paste it into `.env`

### Option 2: Build manually

If Code View import doesn't work, build the flows using the visual designer.
The JSON files show the exact filter queries, field selections, and expressions.

## Flow 1: PRICE SMS - Read (`pa-flow-read.json`)

**Trigger**: HTTP POST with `action` parameter

**Logic**: Switch on `action`, each case does a SharePoint "Get items" query:

| Action | List | Filter | Select | Top |
|--------|------|--------|--------|-----|
| `get_sms_flags` | PRICECalendar | `EventDate ge [now]` | Id, SMS_x0020_Reminder | 500 |
| `has_reminder` | SMS Reminder Log | `CalendarEventID eq X and ReminderType eq Y` | Id | 1 |
| `event_has_response` | SMS Reminder Log | `CalendarEventID eq X and ResponseStatus ne 'pending' and ne 'no_response'` | Id | 1 |
| `find_pending` | SMS Reminder Log | `PhoneHash eq X and ResponseStatus eq 'pending'` (order: Created desc) | Id, SubjectID, StudyCode, ExperimenterEmail | 1 |
| `get_expired_pending` | SMS Reminder Log | `ResponseStatus eq 'pending' and EventStart lt [now]` | Id, SubjectID | 500 |
| `get_status_counts` | SMS Reminder Log | (none) | ResponseStatus | 5000 |

**Response**: Always `{"items": [...]}` with raw SharePoint items. Python handles all parsing.

## Flow 2: PRICE SMS - Write (`pa-flow-write.json`)

**Trigger**: HTTP POST with `action` parameter

**Logic**: Switch on `action`:

### `log_reminder` — Create item in SMS Reminder Log
Fields set from request body: Title, SubjectID, StudyCode, VisitName, EventStart, Location,
ExperimenterEmail, ReminderType, ResponseStatus (="pending"), MosioTransactionID,
CalendarEventID, PhoneHash

**Response**: `{"item_id": <new ID>, "success": true}`

### `update_response` — Update existing item
Updates: ResponseStatus, ResponseText, ResponseAt (= utcNow())

**Response**: `{"success": true}`

## SharePoint List GUIDs (PRICE site)

These are embedded in the flow definitions:
- PRICECalendar: `4003c791-6d6a-461b-a546-decff942678a`
- SMS Reminder Log: `1a1822ab-bd33-4500-aafc-ab71ab2f6fbb`

## After Building

1. Copy each flow's HTTP POST URL
2. Add to `.env`:
   ```
   PA_READ_FLOW_URL=https://prod-XX.westus.logic.azure.com:443/workflows/...
   PA_WRITE_FLOW_URL=https://prod-XX.westus.logic.azure.com:443/workflows/...
   ```
3. Test: `python -m price_calendar check-config`
4. Test: `python -m price_calendar status`
