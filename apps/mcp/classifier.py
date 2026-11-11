"""Friendly-vs-functional classifier for MCP chat.

A greeting ("hi") must never reach the tool parser: the model used to
answer it with whatever tool looked closest ("You teach 1 offerings...").
This classifier runs in ChatView before any LLM call, so small talk gets a
small-talk answer and only real work reaches the tools.

Rule-based on purpose: it is deterministic, costs no LLM call, and cannot
hallucinate. A message is friendly only when it contains NO functional word
(attendance, marks, quiz, ...) and every word is small talk. Anything with
a functional word is functional, even when it starts with "hi".
"""

from __future__ import annotations

import re

# Words that always mean work, checked as whole words. "help" is deliberately
# absent: "can you help me" is friendly, "help me mark attendance" is
# functional because "attendance" is here.
FUNCTIONAL_WORDS = {
    "attendance", "absent", "present", "mark", "marks", "quiz", "mid",
    "midterm", "final", "assignment", "assignments", "cgpa", "forecast",
    "report", "reports", "class", "classes", "course", "courses", "section",
    "sec", "students", "student", "below", "defaulter", "defaulters",
    "department", "departments", "curriculum", "faculty", "teacher",
    "teachers", "offering", "offerings", "batch", "percentage", "percent",
    "list", "show", "give", "bring", "enroll", "enrolled", "enrolment",
    "enrollment", "timetable", "schedule", "exam", "exams", "result",
    "results", "grade", "grades", "fee", "fees", "holiday", "holidays",
    "date", "dates", "room", "lecture", "lectures",
}

FUNCTIONAL_PHRASES = {
    "how many", "out of", "my cgpa", "my attendance", "my marks",
    "my classes", "my courses", "my forecast",
}

# Every word of a friendly message must come from here (after the functional
# check above has already run). Generous on purpose: a functional word
# anywhere already forces "functional", so this set cannot swallow real work.
SMALL_TALK_WORDS = {
    "hi", "hii", "hello", "helloo", "hey", "heyy", "salam", "salaam", "aoa",
    "assalam", "assalamualaikum", "assalamoalaikum", "o", "alaikum",
    "waalaikum", "wallaikum", "good", "morning", "afternoon", "evening",
    "day", "how", "are", "you", "u", "r", "doing", "today", "whats",
    "what's", "what", "up", "who", "is", "the", "assistant", "ai", "can",
    "could", "would", "do", "does", "help", "me", "with", "please", "pls",
    "thanks", "thank", "shukriya", "shukran", "bye", "goodbye", "allah",
    "hafiz", "khuda", "kya", "haal", "hai", "hain", "kese", "kaise",
    "kaisay", "kaisa", "ho", "aap", "ap", "sir", "madam", "ok", "okay",
    "great", "nice", "fine", "well", "and", "i", "am", "m", "feeling",
    "your", "name", "tell", "about", "yourself", "there", "everyone",
    "so", "much", "very", "dear", "bro", "yar", "yaar", "sweet", "cool",
    "awesome", "perfect", "sure", "yeah", "yes", "no", "hmm", "oh",
    "wow", "lol", "hehe", "welcome",
}

_THANKS_WORDS = {"thanks", "thank", "shukriya", "shukran"}
_FAREWELL_WORDS = {"bye", "goodbye", "allah", "hafiz", "khuda"}

_WORD_RE = re.compile(r"[a-z0-9']+")


def _normalize(text: str) -> str:
    return " ".join(_WORD_RE.findall((text or "").casefold()))


def classify_message(text: str) -> str:
    """Return "greeting", "thanks", "farewell" or "functional"."""
    normalized = _normalize(text)
    if not normalized:
        return "functional"
    words = normalized.split()
    if any(word in FUNCTIONAL_WORDS for word in words):
        return "functional"
    if any(phrase in normalized for phrase in FUNCTIONAL_PHRASES):
        return "functional"
    if not all(word in SMALL_TALK_WORDS for word in words):
        return "functional"
    if any(word in _THANKS_WORDS for word in words):
        return "thanks"
    if any(word in _FAREWELL_WORDS for word in words):
        return "farewell"
    return "greeting"
