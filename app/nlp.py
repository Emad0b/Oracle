"""Small spaCy intent layer for deterministic local capabilities."""

from __future__ import annotations

import spacy
from spacy.matcher import Matcher

_nlp = spacy.blank("en")
_matcher = Matcher(_nlp.vocab)
_matcher.add(
    "JOB_TRIAGE",
    [
        [{"LOWER": {"IN": ["label", "categorize", "classify", "sort", "triage"]}},
         {"OP": "*", "IS_ALPHA": True},
         {"LOWER": {"IN": ["job", "jobs", "application", "applications", "email", "emails", "gmail"]}}],
        [{"LOWER": {"IN": ["job", "jobs", "application", "applications"]}},
         {"OP": "*", "IS_ALPHA": True},
         {"LOWER": {"IN": ["label", "categorize", "classify", "sort", "triage"]}}],
    ],
)


def is_job_triage_request(text: str) -> bool:
    """Recognize simple natural-language requests for job-email triage."""
    doc = _nlp(text)
    if _matcher(doc):
        lowered = text.lower()
        return any(
            term in lowered
            for term in ("job", "application", "email", "gmail", "offer", "declin", "response")
        )
    return False


def is_show_job_chart_request(text: str) -> bool:
    """Recognize requests to reopen the latest job pie chart."""
    lowered = text.lower()
    wants_chart = any(term in lowered for term in ("chart", "pie", "graph", "visual"))
    jobby = any(term in lowered for term in ("job", "application", "triage", "offer", "declin"))
    return wants_chart and (jobby or "show" in lowered)
