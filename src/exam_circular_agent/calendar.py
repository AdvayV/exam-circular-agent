"""Match exam dates and prepare an updated copy of an iCalendar file."""

import re
from collections import Counter, defaultdict
from copy import deepcopy
from dataclasses import dataclass
from datetime import UTC, datetime

from icalendar import Calendar, Event

from .schedule import Exam, Schedule

COURSE_PREFIX = re.compile(r"^\[([A-Za-z0-9][A-Za-z0-9-]*)\]")
RECURRENCE_FIELDS = {"RRULE", "RDATE", "EXDATE", "EXRULE", "RECURRENCE-ID"}


@dataclass(frozen=True)
class Change:
    uid: str
    summary: str
    old_start: datetime
    old_end: datetime
    exam: Exam


@dataclass(frozen=True)
class Review:
    changes: tuple[Change, ...] = ()
    notes: tuple[str, ...] = ()


def _normalise(value: str) -> str:
    return " ".join(value.casefold().split())


def _course_code(event: Event) -> str | None:
    explicit = event.get("X-COURSE-CODE")
    if explicit is not None:
        return str(explicit).strip().upper()
    match = COURSE_PREFIX.match(str(event.get("SUMMARY", "")))
    return match[1].upper() if match else None


def _time(event: Event, key: str) -> datetime | None:
    value = getattr(event.get(key), "dt", None)
    if isinstance(value, datetime) and value.utcoffset() is not None:
        return value
    return None


def compare_schedule(
    calendar: Calendar, schedule: Schedule, *, programme: str, term: str
) -> Review:
    if schedule.status != "applicable":
        return Review(notes=schedule.notes or ("The circular needs manual review.",))
    if (_normalise(schedule.programme), _normalise(schedule.term)) != (
        _normalise(programme), _normalise(term)
    ):
        return Review(notes=("The circular's programme or term does not match.",))

    events_by_code = defaultdict(list)
    events = calendar.walk("VEVENT")
    uid_counts = Counter(str(event.get("UID", "")) for event in events)
    for event in events:
        if code := _course_code(event):
            events_by_code[code].append(event)

    exams_by_code: dict[str, list[Exam]] = defaultdict(list)
    for exam in schedule.exams:
        exams_by_code[exam.course_code.upper()].append(exam)

    changes = []
    notes = list(schedule.notes)
    for code, exams in exams_by_code.items():
        candidates = events_by_code[code]
        if not candidates:
            continue
        if len(candidates) != 1:
            notes.append(f"{code}: multiple calendar events match. Review manually.")
            continue

        if len({(exam.starts_at, exam.ends_at) for exam in exams}) != 1:
            notes.append(f"{code}: circular contains conflicting exam times. Review manually.")
            continue

        exam = exams[0]
        event = candidates[0]
        uid = str(event.get("UID", ""))
        start, end = _time(event, "DTSTART"), _time(event, "DTEND")
        if (
            not uid
            or uid_counts[uid] != 1
            or RECURRENCE_FIELDS.intersection(event.keys())
            or "DURATION" in event
            or start is None
            or end is None
            or end <= start
        ):
            notes.append(f"{code}: calendar event cannot be updated reliably. Review manually.")
            continue

        if (start, end) != (exam.starts_at, exam.ends_at):
            changes.append(Change(uid, str(event.get("SUMMARY", code)), start, end, exam))
    return Review(tuple(changes), tuple(notes))


def revise_calendar(calendar: Calendar, review: Review, *, now: datetime) -> Calendar:
    revised = deepcopy(calendar)
    events_by_uid = {str(event.get("UID", "")): event for event in revised.walk("VEVENT")}
    for change in review.changes:
        event = events_by_uid[change.uid]
        sequence = int(event.get("SEQUENCE", 0)) + 1
        for key, value in (
            ("DTSTART", change.exam.starts_at.astimezone(UTC)),
            ("DTEND", change.exam.ends_at.astimezone(UTC)),
            ("DTSTAMP", now.astimezone(UTC)),
            ("SEQUENCE", sequence),
        ):
            event.pop(key, None)
            event.add(key, value)
    return revised
