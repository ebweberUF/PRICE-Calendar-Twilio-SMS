# PRICE Calendar SMS Reminders

## Overview
Stateless Python service that sends appointment reminders to study participants via Twilio SMS and notifies lead experimenters of responses.

## Architecture (fully stateless — no local files, no local DB)
- Pulls upcoming events from PRICE-Intranet calendar API
- All SharePoint operations go through **Power Automate HTTP flows** (no direct SP auth)
- Looks up phone numbers from REDCap on-demand (no PHI at rest)
- Sends SMS via Twilio REST API (Messaging Service, local number 352-278-9116)
- Polls Twilio inbound messages for participant replies (last 2h window)
- Power Automate watches ResponseStatus changes and emails lead experimenter

## Key Commands
```bash
conda activate price-calendar
python -m price_calendar run          # Run one cycle
python -m price_calendar run --dry-run # Dry run (no sends)
python -m price_calendar send-test    # Test SMS
python -m price_calendar check-config # Validate config
python -m price_calendar status       # Show counts
```

## Config — everything in .env
- `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, `TWILIO_MESSAGING_SERVICE_SID` — Twilio SMS
- `PA_READ_FLOW_URL`, `PA_WRITE_FLOW_URL` — Power Automate HTTP trigger URLs
- `TEAM_EMAILS` — notification recipients
- Study configs loaded from SharePoint SMS Study Config list via PA Read flow

## Key Modules
- `sharepoint_store.py` — all SP operations via Power Automate (dedup, response matching, escalation)
- `scheduler.py` — three-phase orchestration (send → poll → escalate)
- `twilio_client.py` — Twilio REST calls, phone normalization, response parsing
- `calendar_client.py` — parses SharePoint calendar items into events
- `redcap_client.py` — on-demand phone lookup from env var tokens
- `config.py` — loads everything from env vars, no local file paths

## Deprecated (kept for reference)
- `db.py` — replaced by sharepoint_store.py
- `notifier.py` — consolidated into sharepoint_store.py
- `mosio_client.py` — replaced by twilio_client.py

## A2P 10DLC Registration
- Brand: `BN2c22b0613900db17cd36cf7588d0aa7c` (APPROVED, score 87)
- Campaign: `QE2c6890da8086d771620e9b13fadeba0b` (pending carrier review)
- Messaging Service: `MG6b58e8b163850232d55cf14bd855dc37`
- Numbers: +13522789116 (local, 10DLC), +18333105525 (toll-free)
