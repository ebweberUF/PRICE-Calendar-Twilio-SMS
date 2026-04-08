# PRICE SMS Reminders — Operations Guide

## What This System Does

Sends SMS appointment reminders to PRICE clinical study participants and notifies lead experimenters when participants respond. Fully stateless — no local database or files.

## How It Works (End to End)

```
Every 30 minutes (GitHub Actions cron, weekdays 7am-9pm ET):

1. SEND PHASE
   GitHub Actions runner → SharePoint via PA Read flow (get events next 73h)
                         → SharePoint via PA Read flow (check SMS opt-in flags)
                         → SharePoint via PA Read flow (dedup — already sent?)
                         → REDCap API (look up participant phone number)
                         → Twilio API (send SMS)
                         → SharePoint via PA Write flow (log reminder as "pending")

2. POLL PHASE
   GitHub Actions runner → Twilio API (get inbound messages last 2h)
                         → SharePoint via PA Read flow (match phone hash to pending reminder)
                         → SharePoint via PA Write flow (update status + trigger notification email)

3. ESCALATE PHASE
   GitHub Actions runner → SharePoint via PA Read flow (find expired pending reminders)
                         → SharePoint via PA Write flow (mark as "no_response" + notify experimenter)
```

## Where Everything Runs

| Component | Location | Access |
|-----------|----------|--------|
| **Python scheduler** | GitHub Actions (cron) | [Workflow runs](https://github.com/ebweberUF/PRICE-Calendar-Twilio-SMS/actions) |
| **Calendar data** | SharePoint PRICECalendar list (via PA Read flow) | No direct access needed |
| **Twilio SMS** | Twilio cloud | Account SID `ACd60d...` |
| **SharePoint lists** | PRICE SharePoint site | Via Power Automate |
| **PA Read flow** | Power Automate | HTTP trigger (URL in GitHub secret) |
| **PA Write flow** | Power Automate | HTTP trigger (URL in GitHub secret) |
| **REDCap** | UF REDCap | API tokens in SharePoint SMS Study Config list |
| **Study config** | SharePoint "SMS Study Config" list | Managed by study team |

## GitHub Repository

**Repo:** https://github.com/ebweberUF/PRICE-Calendar-Twilio-SMS

### Secrets (Settings → Secrets and variables → Actions)

| Secret | Purpose |
|--------|---------|
| `TWILIO_ACCOUNT_SID` | Twilio account identifier |
| `TWILIO_AUTH_TOKEN` | Twilio API auth |
| `TWILIO_MESSAGING_SERVICE_SID` | Routes SMS through registered Messaging Service |
| `PA_READ_FLOW_URL` | Power Automate read flow HTTP trigger |
| `PA_WRITE_FLOW_URL` | Power Automate write flow HTTP trigger |
| `TEAM_EMAILS` | Notification recipients (comma-separated) |

### Workflow Schedule

File: `.github/workflows/sms-reminder.yml`

- **When:** Every 30 minutes, Monday-Friday, 7:00 AM - 9:00 PM Eastern
- **Cron:** `*/30 11-23,0-1 * * 1-5` (UTC)
- **Manual trigger:** Actions tab → "Run workflow" button

## Twilio A2P 10DLC Registration

| Item | Value | Status |
|------|-------|--------|
| Brand | `BN2c22b0613900db17cd36cf7588d0aa7c` | APPROVED (score 87) |
| Campaign | `QE2c6890da8086d771620e9b13fadeba0b` | Pending carrier review |
| Messaging Service | `MG6b58e8b163850232d55cf14bd855dc37` | Active |
| Local number | +1 (352) 278-9116 | In Messaging Service |
| Toll-free number | +1 (833) 310-5525 | In Messaging Service |

## SharePoint Lists

### PRICECalendar
- Standard calendar list with `SMS_x0020_Reminder` checkbox field
- When checked, participants for that event receive SMS reminders

### SMS Reminder Log
Fields: Title, SubjectID, StudyCode, VisitName, EventStart, Location,
ExperimenterEmail, ReminderType, ResponseStatus, MessageSID,
CalendarEventID, PhoneHash, ResponseText, ResponseAt

### SMS Study Config
Fields: StudyCode, RedcapApiUrl, RedcapApiToken, PhoneField, SubjectIdField, Active

## Power Automate Flows

### PRICE SMS - Read
- **Trigger:** HTTP POST
- **Actions:** Switch on `action` parameter, queries SharePoint lists
- **Returns:** `{"items": [...]}`
- **Spec:** `specs/pa-flow-read.json`

### PRICE SMS - Write
- **Trigger:** HTTP POST
- **Actions:** Creates/updates SharePoint list items, sends notification emails
- **Returns:** `{"success": true, "item_id": ...}`
- **Spec:** `specs/pa-flow-write.json`

### PRICE SMS - Notify (optional)
- **Trigger:** SharePoint item modified (ResponseStatus changed)
- **Action:** Emails lead experimenter with response details
- **Spec:** `specs/pa-flow-notify.json`

## SMS Message Design

- No participant names (HIPAA)
- Max 160 characters
- Response protocol: 1=Confirm, 2=Reschedule, 3=Cancel
- Two reminder windows: 72h (36-73h before) and 24h (4-36h before)
- Unrecognized replies get a clarification SMS

## Troubleshooting

### Check workflow logs
```
gh run list --workflow=sms-reminder.yml --limit=5
gh run view <run-id> --log
```

### Manual run
```
gh workflow run "PRICE SMS Reminders"
```

### Test locally
```bash
conda activate price-calendar
python -m price_calendar check-config   # Validate all connections
python -m price_calendar run --dry-run  # Simulate without sending
python -m price_calendar send-test 3525551234  # Send test SMS
python -m price_calendar status         # Show reminder counts
```

### Common issues
- **PA flow URL expired:** Power Automate URLs don't expire, but if a flow is modified the URL may change. Update the GitHub secret.
- **Twilio campaign not approved:** Check campaign status — 10DLC local number won't send until campaign is VERIFIED. Toll-free works immediately.
- **No events found:** Check that PRICECalendar list items have `SMS_x0020_Reminder` checked and valid `subjectId` values.
