"""CLI entry point for PRICE Calendar SMS reminders."""

from __future__ import annotations

import argparse
import logging
import sys

from .config import Config
from .twilio_client import TwilioClient, normalize_phone
from .scheduler import run_cycle
from .sharepoint_store import SharePointStore


def setup_logging() -> None:
    """Configure logging to stdout only — no local files."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=[
            logging.StreamHandler(sys.stdout),
        ],
    )


def cmd_run(args: argparse.Namespace) -> None:
    """Run one send/poll/escalate cycle."""
    config = Config.load()
    summary = run_cycle(config, dry_run=args.dry_run)
    if args.dry_run:
        print("[DRY RUN] No messages were actually sent.")
    print(f"Cycle complete: {summary}")


def cmd_send_test(args: argparse.Namespace) -> None:
    """Send a test SMS to verify Twilio config."""
    config = Config.load()
    twilio = TwilioClient(
        config.twilio_account_sid,
        config.twilio_auth_token,
        config.twilio_messaging_service_sid,
    )

    phone = normalize_phone(args.phone)
    message = "PRICE Calendar test message. SMS reminders are configured and working. Reply STOP to opt out."

    print(f"Sending test SMS to {phone}...")
    result = twilio.send_sms(phone, message)

    if result.success:
        print(f"Success! Message SID: {result.message_sid}")
    else:
        print(f"Failed: [{result.error_code}] {result.error_message}")
        sys.exit(1)


def cmd_check_config(args: argparse.Namespace) -> None:
    """Validate settings, REDCap tokens, Twilio creds, Power Automate flows."""
    print("Checking configuration...")
    errors: list[str] = []

    try:
        config = Config.load()
        print(f"  Twilio SID:    ...{config.twilio_account_sid[-8:]}")
        print(f"  Twilio MsgSvc: ...{config.twilio_messaging_service_sid[-8:]}")
        print(f"  Calendar URL:  {config.calendar_api_url}")
        print(f"  PA Read flow:  {'set' if config.pa_read_flow_url else 'MISSING'}")
        print(f"  PA Write flow: {'set' if config.pa_write_flow_url else 'MISSING'}")
        print(f"  Studies:       {list(config.study_mappings.keys())}")
    except Exception as e:
        errors.append(f"Config load failed: {e}")
        print(f"  FAIL: {e}")

    if not errors:
        # Check study configs loaded from SharePoint
        for code, mapping in config.study_mappings.items():
            has_token = bool(mapping.redcap_api_token and mapping.redcap_api_token != "REPLACE_WITH_TOKEN")
            print(f"  Study {code}:    phone={mapping.phone_field}, REDCap={'configured' if has_token else 'MISSING TOKEN'}")
            if not has_token:
                errors.append(f"Missing REDCap token for {code} in SMS Study Config list")

        # Test Twilio API
        twilio = TwilioClient(
            config.twilio_account_sid,
            config.twilio_auth_token,
            config.twilio_messaging_service_sid,
        )
        twilio_ok, twilio_err = twilio.check_connection()
        if twilio_ok:
            print("  Twilio API:    connected")
        else:
            errors.append(f"Twilio API: {twilio_err}")
            print(f"  Twilio API:    FAILED ({twilio_err})")

        # Test Power Automate read flow
        store = SharePointStore(config.pa_read_flow_url, config.pa_write_flow_url)
        counts = store.get_status_counts()
        if counts is not None:
            print("  PA Read flow:  connected")
        else:
            errors.append("Power Automate read flow failed")
            print("  PA Read flow:  FAILED")

    if errors:
        print(f"\n{len(errors)} error(s) found:")
        for e in errors:
            print(f"  - {e}")
        sys.exit(1)
    else:
        print("\nAll checks passed.")


def cmd_status(args: argparse.Namespace) -> None:
    """Show reminder counts by status (from SharePoint via Power Automate)."""
    config = Config.load()
    store = SharePointStore(config.pa_read_flow_url, config.pa_write_flow_url)
    counts = store.get_status_counts()

    total = sum(counts.values())
    print(f"PRICE Calendar SMS Reminders — {total} total")
    print("-" * 40)
    for status in ["pending", "confirmed", "reschedule", "cancel", "no_response"]:
        count = counts.get(status, 0)
        print(f"  {status:15s}  {count}")


def main() -> None:
    """Main CLI entry point."""
    setup_logging()

    parser = argparse.ArgumentParser(
        prog="price_calendar",
        description="PRICE Calendar SMS appointment reminders via Twilio",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # run
    p_run = sub.add_parser("run", help="Run one send/poll/escalate cycle")
    p_run.add_argument("--dry-run", action="store_true", help="Log without sending")
    p_run.set_defaults(func=cmd_run)

    # send-test
    p_test = sub.add_parser("send-test", help="Send a test SMS")
    p_test.add_argument("phone", help="Phone number to send test to (e.g., 3525551234)")
    p_test.set_defaults(func=cmd_send_test)

    # check-config
    p_check = sub.add_parser("check-config", help="Validate configuration")
    p_check.set_defaults(func=cmd_check_config)

    # status
    p_status = sub.add_parser("status", help="Show reminder counts")
    p_status.set_defaults(func=cmd_status)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
