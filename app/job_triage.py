"""Conservative classification of recent job-application Gmail threads."""

from __future__ import annotations

import base64
import re
import time
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from typing import Any

from app.google_services import (
    get_email_thread,
    get_or_create_gmail_label,
    list_email_thread_ids,
    set_thread_category_label,
)

LABELS = {
    "offer": "Oracle/Jobs/Offer",
    "declined": "Oracle/Jobs/Declined",
    "responded": "Oracle/Jobs/Responded",
    "no_response": "Oracle/Jobs/No Response",
    "awaiting_response": "Oracle/Jobs/Awaiting Response",
}
# Silent applications older than this are treated as rejections.
NO_RESPONSE_DAYS = 21

JOB_PLATFORMS = (
    "indeed",
    "linkedin jobs",
    "glassdoor",
    "totaljobs",
    "reed.co.uk",
    "ziprecruiter",
    "workday",
    "greenhouse",
    "lever.co",
    "smartrecruiters",
    "cv-library",
    "seek applications",
    "seek.com.au",
    "greenhouse-mail",
    "myworkday",
)
APPLICATION_EVIDENCE = (
    "application submitted",
    "application was submitted",
    "application has been submitted",
    "application sent",
    "application was sent",
    "your application to",
    "your application for",
    "you applied to",
    "you applied for",
    "thanks for applying",
    "thank you for applying",
    "received your application",
    "application received",
    "we have received your application",
    "we've received your application",
    "applied on indeed",
    "viewed your application",
)
JOB_CONTEXT = (
    "job title",
    "job id",
    "job reference",
    "employment",
    "vacancy",
    "hiring manager",
    "recruiter",
    "recruitment",
    "candidate",
    "candidacy",
    "interview",
    "position",
    "role at",
    "career",
)
NON_JOB_CONTEXT = (
    "roommate",
    "room mate",
    "flatmate",
    "flat mate",
    "room for rent",
    "apartment",
    "property",
    "tenancy",
    "tenant",
    "lease application",
    "rental application",
    "housing application",
    "advertisement",
    "classified ad",
    "marketplace",
    "promoted",
    "sponsored",
    "unsubscribe from these ads",
    "job alert",
    "new jobs",
    "terms of service",
    "privacy policy update",
    "passport number",
    "passport application",
    "visa application centre",
    "visa appointment",
    "immigration application",
    "complete your application",
    "still accepting applications",
    "don't forget to submit",
    "confirm your identity",
    "verify your candidate account",
)
OFFER_TERMS = (
    "offer of employment",
    "pleased to offer you",
    "happy to offer you",
    "delighted to offer you",
    "offer letter",
    "conditional offer",
    "job offer",
    "extend an offer to you",
    "extending an offer to you",
    "formal offer",
)
EXPLICIT_OFFER_TERMS = tuple(term for term in OFFER_TERMS if term != "job offer")
DECLINE_TERMS = (
    "regret to inform",
    "we regret to",
    "we regret that",
    "regretfully",
    "regrettably",
    "not moving forward",
    "will not be moving forward",
    "won't be moving forward",
    "will not be taking your application forward",
    "not be taking your application forward",
    "not progressing",
    "will not be progressing",
    "isn't progressing",
    "isn’t progressing",
    "unlikely to progress",
    "not proceed with your",
    "decided not to proceed",
    "decided not to move forward",
    "will not proceed with your candidacy",
    "move forward with other",
    "pursue other candidates",
    "moving forward with other candidates",
    "chosen to move forward with other",
    "unable to offer you",
    "cannot offer you",
    "you have not been selected",
    "you were not selected",
    "you are not selected",
    "have not been selected",
    "not been selected",
    "position has been filled",
    "role has been filled",
    "vacancy has been filled",
    "position is no longer available",
    "role is no longer available",
    "application was unsuccessful",
    "application unsuccessful",
    "unsuccessful on this occasion",
    "not successful this time",
    "were not successful",
    "will not be inviting",
    "not invite you to interview",
    "no longer under consideration",
    "removed from consideration",
    "not the right fit",
    "not a match for",
    "we will not be offering",
    "won't be offering",
    "decline your application",
    "reject your application",
    "application has been rejected",
    "we must decline",
)
DECLINE_SOFT = ("unfortunately", "we regret", "i regret", "regrettably")
DECLINE_CONTEXT = (
    "not proceed",
    "not moving",
    "not progress",
    "other candidate",
    "another candidate",
    "you have not been selected",
    "you were not selected",
    "unsuccessful",
    "not successful",
    "filled",
    "not invite",
    "no longer",
    "not offer",
    "cannot offer",
    "unable to offer",
    "reject",
    "declin",
    "not a fit",
    "not the right",
    "candidacy",
)
# Receipts often say "if you are not selected, check our jobs page".
# That is hypothetical, not a rejection.
HYPOTHETICAL_DECLINE = (
    "if you are not selected",
    "if you're not selected",
    "if you are not successful",
    "if your application is unsuccessful",
    "should you not be selected",
    "if not selected",
    "in the event you are not selected",
    "if we do not select",
    "if your qualifications match",
    "if you are a match",
)
AUTOMATED_ACKNOWLEDGEMENT = (
    "application submitted",
    "application sent",
    "application was sent",
    "application received",
    "received your application",
    "we received your application",
    "our team will review",
    "will be in touch if",
    "thanks for applying",
    "thank you for applying",
    "thank you for your application",
    "we will review your application",
    "we'll review your application",
    "application is being reviewed",
    "application status",
    "application confirmation",
    "viewed your application",
    "do not reply",
    "no-reply",
    "noreply",
)
MEANINGFUL_RESPONSE = (
    "interview",
    "phone screen",
    "screening call",
    "schedule a call",
    "availability",
    "next stage",
    "next step",
    "assessment",
    "technical test",
    "invite you",
    "shortlisted",
    "follow up",
    "follow-up",
)
DIRECT_CONTACT = (
    "message from",
    "sent you a message",
    "has messaged you",
    "would like to invite you",
    "invite you to interview",
    "invite you to the next",
    "next stage of our recruitment",
    "schedule your interview",
    "schedule an interview",
    "please provide your availability",
    "kindly provide us with",
    "salary expectations",
    "screening and shortlisting",
    "please reply to this email with your responses",
)


def _decode_body(payload: dict[str, Any]) -> str:
    data = payload.get("body", {}).get("data")
    if data:
        try:
            return base64.urlsafe_b64decode(data.encode()).decode("utf-8", errors="replace")
        except (ValueError, TypeError):
            return ""
    return "\n".join(_decode_body(part) for part in payload.get("parts") or [])


def _headers(message: dict[str, Any]) -> dict[str, str]:
    return {
        item["name"].lower(): item["value"]
        for item in message.get("payload", {}).get("headers", [])
    }


def _message_date(message: dict[str, Any]) -> datetime | None:
    value = _headers(message).get("date")
    if not value:
        return None
    try:
        return parsedate_to_datetime(value).astimezone(timezone.utc)
    except (TypeError, ValueError):
        return None


def _text(message: dict[str, Any]) -> str:
    headers = _headers(message)
    value = " ".join(
        (
            headers.get("from", ""),
            headers.get("to", ""),
            headers.get("subject", ""),
            message.get("snippet", ""),
            _decode_body(message.get("payload", {})),
        )
    )
    return re.sub(r"\s+", " ", value).lower()


def _is_sent(message: dict[str, Any]) -> bool:
    return "SENT" in message.get("labelIds", [])


def _is_decline(text: str) -> bool:
    cleaned = text
    for phrase in HYPOTHETICAL_DECLINE:
        cleaned = cleaned.replace(phrase, " ")
    if any(term in cleaned for term in DECLINE_TERMS):
        return True
    return any(term in cleaned for term in DECLINE_SOFT) and any(
        cue in cleaned for cue in DECLINE_CONTEXT
    )


def _has_application_evidence(message: dict[str, Any]) -> bool:
    text = _text(message)
    if any(term in text for term in NON_JOB_CONTEXT):
        return False
    direct = any(term in text for term in APPLICATION_EVIDENCE)
    platform = any(term in text for term in JOB_PLATFORMS)
    context = any(term in text for term in JOB_CONTEXT)
    sent_application = _is_sent(message) and (
        "application" in text or "applying for" in text or "apply for" in text
    )
    outcome_application = (
        "application" in text or "candidate" in text or "candidacy" in text
    ) and (
        _is_decline(text) or any(term in text for term in EXPLICIT_OFFER_TERMS)
    )
    return direct or sent_application or outcome_application or (platform and context)


def _is_automated_acknowledgement(message: dict[str, Any]) -> bool:
    text = _text(message)
    platform_sender = any(term in text for term in JOB_PLATFORMS)
    acknowledgement = any(term in text for term in AUTOMATED_ACKNOWLEDGEMENT)
    # Rejections and explicit offers remain outcomes even when an ATS sends them.
    if any(term in text for term in EXPLICIT_OFFER_TERMS) or _is_decline(text):
        return False
    # Platform receipts are application evidence even if the quoted advert says
    # "job offers benefits".
    if platform_sender and acknowledgement:
        return True
    if platform_sender and not any(term in text for term in DIRECT_CONTACT):
        return True
    # Recruiter messages often say "received your application" and then invite
    # you to a next stage. That is a real reply, not an automated receipt.
    if any(term in text for term in DIRECT_CONTACT):
        return False
    if any(term in text for term in MEANINGFUL_RESPONSE):
        return False
    if acknowledgement:
        return True
    return "no-reply" in text or "noreply" in text


def _classify_thread_details(
    thread: dict[str, Any],
    now: datetime,
) -> tuple[str | None, datetime | None, str]:
    messages = thread.get("messages", [])
    application_messages = [message for message in messages if _has_application_evidence(message)]
    if not application_messages:
        return None, None, ""

    application_dates = [
        date for date in (_message_date(message) for message in application_messages) if date
    ]
    application_date = min(application_dates) if application_dates else None

    incoming = [message for message in messages if not _is_sent(message)]
    # Outcomes only count in incoming messages. An Indeed application
    # confirmation can contain words such as "offer" from the original advert,
    # but it is never itself an offer.
    meaningful_incoming = [
        message for message in incoming if not _is_automated_acknowledgement(message)
    ]
    if any(any(term in _text(message) for term in OFFER_TERMS) for message in meaningful_incoming):
        return "offer", application_date, "explicit_offer"
    if any(_is_decline(_text(message)) for message in meaningful_incoming):
        return "declined", application_date, "explicit_rejection"
    if meaningful_incoming:
        return "responded", application_date, "employer_reply"

    if application_date and now - application_date >= timedelta(days=NO_RESPONSE_DAYS):
        return "declined", application_date, "no_reply_after_21_days"
    return "awaiting_response", application_date, "waiting"


def _item(
    thread: dict[str, Any],
    category: str,
    application_date: datetime | None,
    reason: str = "",
) -> dict[str, str]:
    messages = thread.get("messages", [])
    application_message = next(
        (message for message in messages if _has_application_evidence(message)),
        messages[0] if messages else {},
    )
    incoming = [message for message in messages if not _is_sent(message)]
    if category == "offer":
        preview_message = next(
            (
                message
                for message in reversed(incoming)
                if any(term in _text(message) for term in OFFER_TERMS)
            ),
            application_message,
        )
    elif category == "declined":
        preview_message = next(
            (message for message in reversed(incoming) if _is_decline(_text(message))),
            application_message,
        )
    elif category == "responded":
        preview_message = next(
            (
                message
                for message in reversed(incoming)
                if not _is_automated_acknowledgement(message)
            ),
            application_message,
        )
    else:
        preview_message = application_message

    app_headers = _headers(application_message)
    preview_headers = _headers(preview_message)
    return {
        "thread_id": str(thread["id"]),
        "message_id": str(preview_message.get("id", "")),
        "subject": app_headers.get("subject", preview_headers.get("subject", "(no subject)")),
        "from": preview_headers.get("from", "Unknown"),
        "application_date": application_date.date().isoformat() if application_date else "",
        "category": category,
        "reason": reason,
    }


def _metadata_text(thread: dict[str, Any]) -> str:
    parts: list[str] = []
    for message in thread.get("messages", []):
        headers = _headers(message)
        parts.extend(
            (
                headers.get("from", ""),
                headers.get("subject", ""),
                message.get("snippet", ""),
            )
        )
    return re.sub(r"\s+", " ", " ".join(parts)).lower()


def _might_be_job_thread(thread: dict[str, Any]) -> bool:
    """Cheap subject/snippet check before paying for a full message download."""
    text = _metadata_text(thread)
    needles = (
        *JOB_PLATFORMS,
        *APPLICATION_EVIDENCE,
        *JOB_CONTEXT,
        *MEANINGFUL_RESPONSE,
        "application",
        "applying",
        "applied",
        "recruit",
        "offer",
        "rejected",
        "unsuccessful",
    )
    return any(term in text for term in needles)


def _items_by_thread(result: dict[str, Any] | None) -> dict[str, dict[str, str]]:
    if not result:
        return {}
    tracked: dict[str, dict[str, str]] = {}
    for category in LABELS:
        for item in result.get(category) or []:
            thread_id = str(item.get("thread_id") or "")
            if thread_id:
                tracked[thread_id] = dict(item)
    return tracked


def _parse_snapshot_time(result: dict[str, Any] | None) -> datetime | None:
    if not result:
        return None
    raw = result.get("scanned_until")
    if isinstance(raw, str) and raw:
        try:
            parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            return parsed.astimezone(timezone.utc)
        except ValueError:
            pass
    period_end = result.get("period_end")
    if isinstance(period_end, str) and period_end:
        try:
            # End of the last snapshot day so the next run only pulls newer mail.
            return datetime.strptime(period_end, "%Y-%m-%d").replace(
                hour=23,
                minute=59,
                second=59,
                tzinfo=timezone.utc,
            )
        except ValueError:
            return None
    return None


def _apply_local_timeout(item: dict[str, str], now: datetime) -> dict[str, str]:
    """Reclassify awaiting applications that crossed the silence window."""
    if item.get("category") != "awaiting_response":
        return item
    raw_date = item.get("application_date") or ""
    if not raw_date:
        return item
    try:
        application_date = datetime.strptime(raw_date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    except ValueError:
        return item
    if now - application_date >= timedelta(days=NO_RESPONSE_DAYS):
        updated = dict(item)
        updated["category"] = "declined"
        updated["reason"] = "no_reply_after_21_days"
        return updated
    return item


def _bucket_items(tracked: dict[str, dict[str, str]]) -> dict[str, list[dict[str, str]]]:
    classified: dict[str, list[dict[str, str]]] = {name: [] for name in LABELS}
    for item in tracked.values():
        category = item.get("category")
        if category in classified:
            classified[category].append(item)
    for items in classified.values():
        items.sort(key=lambda row: row.get("application_date") or "", reverse=True)
    return classified


def _prune_outside_window(
    tracked: dict[str, dict[str, str]],
    window_start: datetime,
) -> dict[str, dict[str, str]]:
    kept: dict[str, dict[str, str]] = {}
    start_day = window_start.date().isoformat()
    for thread_id, item in tracked.items():
        app_date = item.get("application_date") or ""
        if not app_date or app_date >= start_day:
            kept[thread_id] = item
    return kept


def _load_threads_for_triage(query: str, known_job_ids: set[str] | None = None) -> list[dict[str, Any]]:
    known_job_ids = known_job_ids or set()
    thread_ids = list_email_thread_ids(query)
    print(f"Found {len(thread_ids)} threads to check since last snapshot.")
    threads: list[dict[str, Any]] = []
    for index, thread_id in enumerate(thread_ids, start=1):
        if thread_id in known_job_ids:
            threads.append(get_email_thread(thread_id, fmt="full"))
            time.sleep(0.15)
        else:
            preview = get_email_thread(thread_id, fmt="metadata")
            if _might_be_job_thread(preview):
                threads.append(get_email_thread(thread_id, fmt="full"))
                time.sleep(0.15)
            else:
                threads.append(preview)
        if index % 50 == 0:
            print(f"Checked {index}/{len(thread_ids)} threads…")
    return threads


def triage_job_application_emails(
    months: int = 2,
    apply_labels: bool = True,
    full_rescan: bool = False,
) -> dict[str, Any]:
    """Classify job applications using an incremental Gmail snapshot.

    Each run saves a snapshot. Later runs only download mail since that
    snapshot, re-check tracked threads that received new messages, apply
    21-day timeouts locally, and update Gmail labels when categories change.
    """
    from app.job_chart import load_triage_result, save_triage_result

    months = max(1, min(months, 12))
    now = datetime.now(timezone.utc)
    window_start = now - timedelta(days=months * 30)
    previous = None if full_rescan else load_triage_result()
    previous_tracked = _items_by_thread(previous)
    last_scan = None if full_rescan else _parse_snapshot_time(previous)

    if last_scan is None:
        mode = "full"
        query_start = window_start
        print(
            f"Building full snapshot for the last {months} months "
            f"(after:{query_start.strftime('%Y/%m/%d')})…"
        )
    else:
        mode = "incremental"
        # Overlap one day so same-day mail near the previous cutoff is not missed.
        query_start = max(window_start, last_scan - timedelta(days=1))
        print(
            f"Incremental refresh since {last_scan.isoformat()} "
            f"(query after:{query_start.strftime('%Y/%m/%d')})…"
        )

    known_job_ids = set(previous_tracked)
    threads = _load_threads_for_triage(
        f"after:{query_start.strftime('%Y/%m/%d')}",
        known_job_ids=known_job_ids,
    )
    scanned_emails = sum(len(thread.get("messages", [])) for thread in threads)
    excluded_threads = 0
    new_count = 0
    updated_count = 0
    label_updates: list[tuple[str, str | None, str | None]] = []

    tracked = dict(previous_tracked)
    fetched_ids: set[str] = set()

    for thread in threads:
        thread_id = str(thread["id"])
        fetched_ids.add(thread_id)
        category, application_date, reason = _classify_thread_details(thread, now)
        previous_item = previous_tracked.get(thread_id)
        previous_category = previous_item.get("category") if previous_item else None

        if category is None:
            excluded_threads += 1
            if previous_item is not None:
                del tracked[thread_id]
                label_updates.append((thread_id, previous_category, None))
                updated_count += 1
            continue

        item = _item(thread, category, application_date, reason)
        tracked[thread_id] = item
        if previous_item is None:
            new_count += 1
            label_updates.append((thread_id, None, category))
        elif previous_category != category:
            updated_count += 1
            label_updates.append((thread_id, previous_category, category))

    # Applications with no new mail still age into the 21-day rejection bucket.
    for thread_id, item in list(tracked.items()):
        if thread_id in fetched_ids:
            continue
        timed_out = _apply_local_timeout(item, now)
        if timed_out.get("category") != item.get("category"):
            tracked[thread_id] = timed_out
            updated_count += 1
            label_updates.append((thread_id, item.get("category"), timed_out.get("category")))

    tracked = _prune_outside_window(tracked, window_start)
    classified = _bucket_items(tracked)

    if apply_labels and label_updates:
        label_ids = {
            category: get_or_create_gmail_label(label_name)
            for category, label_name in LABELS.items()
        }
        all_category_ids = list(label_ids.values())
        print(f"Updating Gmail labels on {len(label_updates)} thread(s)…")
        for thread_id, _old_category, new_category in label_updates:
            if thread_id not in tracked and new_category is not None:
                continue
            set_thread_category_label(
                thread_id=thread_id,
                label_id=label_ids.get(new_category) if new_category else None,
                category_label_ids=all_category_ids,
            )
            time.sleep(0.05)

    total_applications = sum(len(items) for items in classified.values())
    result = {
        "period_start": window_start.date().isoformat(),
        "period_end": now.date().isoformat(),
        "scanned_until": now.isoformat(),
        "scan_mode": mode,
        "no_response_after_days": NO_RESPONSE_DAYS,
        "labels_applied": apply_labels,
        "scanned_threads": len(threads),
        "scanned_emails": scanned_emails,
        "new_applications": new_count,
        "updated_applications": updated_count,
        "relabeled_threads": len(label_updates),
        "total_applications": total_applications,
        "excluded_non_job_threads": excluded_threads,
        **classified,
        "skipped_note": (
            "Incremental snapshot: only mail since the last run is downloaded. "
            "Indeed confirmations count as applications, not offers or replies. "
            "Ads, housing, and roommate mail are excluded. "
            f"Applications with no employer reply after {NO_RESPONSE_DAYS} days "
            "are counted as rejections. Labels update for new mail and category changes."
        ),
    }
    save_triage_result(result)
    print(
        f"Snapshot saved: {total_applications} applications "
        f"({new_count} new, {updated_count} updated, {len(label_updates)} relabeled)."
    )
    return result
