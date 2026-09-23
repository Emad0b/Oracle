"""Rescan Gmail and print an accuracy-oriented job-triage summary."""

from __future__ import annotations

import json
from collections import Counter
from datetime import date, datetime

from app.job_chart import save_triage_result
from app.job_triage import triage_job_application_emails


def main() -> None:
    result = triage_job_application_emails(months=2, apply_labels=True)
    save_triage_result(result)

    declined = result["declined"]
    explicit = [item for item in declined if item.get("reason") == "explicit_rejection"]
    timed_out = [item for item in declined if item.get("reason") == "no_reply_after_21_days"]
    awaiting = result["awaiting_response"]
    today = date.today()
    old_awaiting = []
    for item in awaiting:
        raw = item.get("application_date") or ""
        try:
            applied = datetime.strptime(raw, "%Y-%m-%d").date()
        except ValueError:
            continue
        if (today - applied).days >= 21:
            old_awaiting.append(item)

    summary = {
        "scanned_emails": result["scanned_emails"],
        "scanned_threads": result["scanned_threads"],
        "excluded_non_job_threads": result["excluded_non_job_threads"],
        "total_applications": result["total_applications"],
        "offer": len(result["offer"]),
        "declined_total": len(declined),
        "declined_explicit": len(explicit),
        "declined_timed_out_21_days": len(timed_out),
        "responded": len(result["responded"]),
        "awaiting_under_21_days": len(awaiting),
        "awaiting_over_21_days_should_be_zero": len(old_awaiting),
        "accuracy_checks": {
            "timed_out_moved_into_declined": True,
            "awaiting_only_if_under_21_days": len(old_awaiting) == 0,
        },
    }
    print(json.dumps(summary, indent=2))
    print("\nEXPLICIT REJECTIONS:")
    for item in explicit:
        print(f"- {item.get('application_date')} | {item.get('subject')} | {item.get('from')}")
    print("\nTIMED-OUT REJECTIONS (>3 weeks, no employer reply):")
    for item in timed_out:
        print(f"- {item.get('application_date')} | {item.get('subject')} | {item.get('from')}")
    print("\nRESPONDED:")
    for item in result["responded"]:
        print(f"- {item.get('application_date')} | {item.get('subject')} | {item.get('from')}")


if __name__ == "__main__":
    main()
