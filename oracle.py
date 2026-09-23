#!/usr/bin/env python
"""Oracle text-first LLM assistant."""

from __future__ import annotations

import argparse
import sys


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Oracle text-first LLM assistant")
    parser.add_argument("--terminal", action="store_true", help="Run in the terminal instead of the chat window.")
    parser.add_argument("--connect-google", action="store_true", help="Connect Gmail and Google Calendar, then exit.")
    parser.add_argument("--status", action="store_true", help="Print Google connection status, then exit.")
    parser.add_argument(
        "--triage-job-emails",
        action="store_true",
        help="Label job application threads from the past two months, then show the pie chart.",
    )
    parser.add_argument(
        "--show-job-chart",
        action="store_true",
        help="Refresh from the Gmail snapshot (incremental) and open the pie chart.",
    )
    parser.add_argument(
        "--full-rescan",
        action="store_true",
        help="Ignore the saved snapshot and rescan the full two-month Gmail window.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.connect_google:
        from app.google_auth import GoogleAuthError, connect_google_desktop, google_status

        try:
            connect_google_desktop()
        except GoogleAuthError as exc:
            print(f"Google connect failed: {exc}")
            return 1
        print(f"Connected as {google_status().get('email') or 'Google account'}.")
        return 0

    if args.status:
        from app.google_auth import google_status

        print(google_status())
        return 0

    if args.show_job_chart:
        from app.google_auth import GoogleAuthError
        from app.google_services import GoogleServiceError
        from app.job_chart import load_triage_result, show_job_triage_chart
        from app.job_triage import triage_job_application_emails

        print("Refreshing job-application data from Gmail…")
        try:
            result = triage_job_application_emails(
                months=2,
                apply_labels=True,
                full_rescan=args.full_rescan,
            )
        except GoogleAuthError as exc:
            print(f"Live refresh unavailable: {exc}")
            print("Reconnect Gmail, then run this again:")
            print("  .\\.venv\\Scripts\\python.exe oracle.py --connect-google")
            print("  .\\.venv\\Scripts\\python.exe oracle.py --show-job-chart")
            result = None
        except GoogleServiceError as exc:
            print(f"Live refresh unavailable: {exc}")
            print("Gmail’s per-minute quota was exceeded. Wait a minute, then run:")
            print("  .\\.venv\\Scripts\\python.exe oracle.py --show-job-chart")
            result = None
        if result is None:
            result = load_triage_result()
            if result:
                print("Opening the last saved result (not live Gmail data).")
            else:
                print("No saved result to open.")
                return 1
        show_job_triage_chart(result, parent=None, block=True)
        return 0

    if args.triage_job_emails:
        from app.google_auth import GoogleAuthError
        from app.job_chart import show_job_triage_chart
        from app.job_triage import triage_job_application_emails

        try:
            result = triage_job_application_emails(full_rescan=args.full_rescan)
        except GoogleAuthError as exc:
            print(f"Job-email triage unavailable: {exc}")
            return 1
        print(
            f"{result.get('scan_mode', 'full').title()} snapshot: "
            f"checked {result['scanned_threads']} threads / {result['scanned_emails']} emails; "
            f"{result.get('new_applications', 0)} new, {result.get('updated_applications', 0)} updated, "
            f"{result.get('relabeled_threads', 0)} relabeled; "
            f"{result['total_applications']} applications: "
            f"{len(result['offer'])} offer, {len(result['declined'])} declined "
            f"({sum(1 for item in result['declined'] if item.get('reason') == 'explicit_rejection')} explicit, "
            f"{sum(1 for item in result['declined'] if item.get('reason') == 'no_reply_after_21_days')} timed out), "
            f"{len(result['responded'])} responded/in progress, and "
            f"{len(result['awaiting_response'])} awaiting the 21-day window."
        )
        print("Opening interactive pie chart…")
        show_job_triage_chart(result, parent=None, block=True)
        return 0

    from app.assistant import OracleAssistant

    assistant = OracleAssistant()
    if args.terminal:
        assistant.run_terminal()
    else:
        assistant.run_ui()
    return 0


if __name__ == "__main__":
    sys.exit(main())
