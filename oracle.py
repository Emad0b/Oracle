#!/usr/bin/env python
"""Oracle text-first LLM assistant."""

from __future__ import annotations

import argparse
import sys


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Oracle text-first LLM assistant")
    parser.add_argument("--terminal", action="store_true", help="Run in the terminal instead of the chat window.")
    parser.add_argument("--money", action="store_true", help="Open the local MyMoney desktop workspace without API access.")
    parser.add_argument("--connect-google", action="store_true", help="Connect Gmail and Google Calendar, then exit.")
    parser.add_argument("--status", action="store_true", help="Print Google connection status, then exit.")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.money:
        from app.finance_ui import open_finance
        open_finance()
        return 0
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

    from app.assistant import OracleAssistant

    assistant = OracleAssistant()
    if args.terminal:
        assistant.run_terminal()
    else:
        assistant.run_ui()
    return 0


if __name__ == "__main__":
    sys.exit(main())
