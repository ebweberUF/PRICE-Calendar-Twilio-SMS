# PRICE Calendar SMS Reminders

Stateless service that sends SMS appointment reminders to PRICE clinical study participants via Twilio and notifies lead experimenters when participants respond.

## How It Works

Runs every 30 minutes via GitHub Actions (weekdays 7am-9pm ET):

1. **Send** - Fetches upcoming events from SharePoint, looks up phone numbers from REDCap, sends reminders via Twilio
2. **Poll** - Checks Twilio for participant replies, matches to pending reminders, updates SharePoint
3. **Escalate** - Marks expired pending reminders as no-response, triggers notification to experimenter

All state lives in SharePoint (via Power Automate). No local database or files.

## Architecture

```
GitHub Actions (cron)
  -> SharePoint PRICECalendar list (via PA Read flow)
  -> REDCap API (phone number lookup)
  -> Twilio API (send/receive SMS)
  -> SharePoint SMS Reminder Log (via PA Write flow)
  -> Power Automate notification email to lead experimenter
```

## Setup

### Prerequisites
- Twilio account with A2P 10DLC registration
- Power Automate flows (Read + Write + Notify) connected to PRICE SharePoint site
- REDCap API tokens configured in SharePoint SMS Study Config list
- GitHub repository secrets configured

### GitHub Secrets

| Secret | Purpose |
|--------|---------|
| `TWILIO_ACCOUNT_SID` | Twilio account identifier |
| `TWILIO_AUTH_TOKEN` | Twilio API auth |
| `TWILIO_MESSAGING_SERVICE_SID` | Twilio Messaging Service |
| `PA_READ_FLOW_URL` | Power Automate read flow HTTP trigger |
| `PA_WRITE_FLOW_URL` | Power Automate write flow HTTP trigger |
| `TEAM_EMAILS` | Notification recipients (comma-separated) |

### Local Development

```bash
conda env create -f environment.yml
conda activate price-calendar
cp .env.example .env  # fill in credentials
python -m price_calendar check-config
python -m price_calendar run --dry-run
```

## CLI Commands

```bash
python -m price_calendar run            # Run one cycle
python -m price_calendar run --dry-run   # Simulate without sending
python -m price_calendar send-test PHONE # Send a test SMS
python -m price_calendar check-config    # Validate all connections
python -m price_calendar status          # Show reminder counts
```

## SMS Design

- No participant names in messages (HIPAA)
- 160 character limit
- Response protocol: `1` = Confirm, `2` = Reschedule, `3` = Cancel
- Two reminder windows: 72h and 24h before appointment
- Unrecognized replies get a clarification message

## Project Structure

```
src/price_calendar/
  scheduler.py         # Three-phase orchestration
  twilio_client.py     # Twilio REST API, phone normalization, response parsing
  calendar_client.py   # SharePoint calendar event parsing
  sharepoint_store.py  # All SharePoint ops via Power Automate
  redcap_client.py     # On-demand phone number lookup
  config.py            # Environment variable loading + SharePoint study config
  main.py              # CLI entry points
specs/                 # Power Automate flow definitions and import packages
docs/                  # Operations guide
```

## Documentation

- [Operations Guide](docs/operations.md) - Where everything runs, secrets, troubleshooting
- [Power Automate Flows](specs/power-automate-flows.md) - Flow setup and field reference
