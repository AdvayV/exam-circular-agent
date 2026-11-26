from datetime import UTC, datetime, timedelta

from icalendar import Calendar, Event

from exam_circular_agent.calendar import compare_schedule, revise_calendar
from exam_circular_agent.schedule import Exam, Schedule

PROGRAMME = "Online MCA"
TERM = "Fall 2026"
ORIGINAL = datetime(2026, 11, 28, 4, tzinfo=UTC)
REVISED = datetime(2026, 11, 29, 8, 30, tzinfo=UTC)
STAMP = datetime(2026, 11, 24, 12, tzinfo=UTC)


def make_calendar(*, start=ORIGINAL):
    calendar = Calendar()
    calendar.add("prodid", "-//Exam test//EN")
    calendar.add("version", "2.0")
    event = Event()
    event.add("uid", "exam-1@example.invalid")
    event.add("summary", "[CS101] Machine Learning Exam")
    event.add("dtstamp", STAMP)
    event.add("dtstart", start)
    event.add("dtend", start + timedelta(hours=2))
    event.add("location", "Room 101")
    calendar.add_component(event)
    return calendar


def make_exam(start=REVISED):
    return Exam(
        course_code="CS101",
        starts_at=start,
        ends_at=start + timedelta(hours=2),
        source_page=2,
        source_text="CS101 — 29 November, 14:00",
    )


def make_schedule(*exams, programme=PROGRAMME):
    return Schedule(status="applicable", programme=programme, term=TERM, exams=exams, notes=())


def compare(calendar, schedule):
    return compare_schedule(calendar, schedule, programme=PROGRAMME, term=TERM)


def test_compare_and_export_preserve_identity_and_original():
    original = make_calendar()
    schedule = make_schedule(make_exam())
    review = compare(original, schedule)
    assert len(review.changes) == 1
    assert review.changes[0].exam.source_page == 2
    revised = revise_calendar(original, review, now=STAMP)
    event = Calendar.from_ical(revised.to_ical()).walk("VEVENT")[0]
    assert event.decoded("DTSTART") == REVISED
    assert event["UID"] == "exam-1@example.invalid"
    assert event["LOCATION"] == "Room 101"
    assert event["SEQUENCE"] == 1
    assert original.walk("VEVENT")[0].decoded("DTSTART") == ORIGINAL
    assert compare(revised, schedule).changes == ()


def test_same_course_code_cannot_override_programme_mismatch():
    review = compare(make_calendar(), make_schedule(make_exam(), programme="On-campus MCA"))
    assert review.changes == ()
    assert "does not match" in review.notes[0]


def test_conflicting_source_rows_are_withheld():
    schedule = make_schedule(make_exam(), make_exam(REVISED + timedelta(days=1)))
    review = compare(make_calendar(), schedule)
    assert review.changes == ()
    assert "conflicting" in review.notes[0]


def test_course_without_a_calendar_event_is_reported():
    exam = make_exam().model_copy(update={"course_code": "CS205"})
    review = compare(make_calendar(), make_schedule(exam))
    assert review.changes == ()
    assert review.notes == ("CS205: no matching calendar event. Review manually.",)


def test_recurring_event_is_withheld():
    calendar = make_calendar()
    calendar.walk("VEVENT")[0].add("rrule", {"freq": "weekly"})
    review = compare(calendar, make_schedule(make_exam()))
    assert review.changes == ()
    assert "Review manually" in review.notes[0]
