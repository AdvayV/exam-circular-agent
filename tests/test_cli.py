import json
from datetime import UTC, datetime

import pytest
from icalendar import Calendar

from exam_circular_agent.cli import main


@pytest.fixture
def inputs(tmp_path):
    calendar = tmp_path / "exam.ics"
    calendar.write_text(
        "\n".join(
            [
                "BEGIN:VCALENDAR",
                "VERSION:2.0",
                "PRODID:-//Exam test//EN",
                "BEGIN:VEVENT",
                "UID:sample@example.invalid",
                "DTSTAMP:20261124T000000Z",
                "DTSTART:20261128T040000Z",
                "DTEND:20261128T060000Z",
                "SUMMARY:[CS101] Exam",
                "END:VEVENT",
                "END:VCALENDAR",
                "",
            ]
        ),
        encoding="utf-8",
    )
    extraction = tmp_path / "extraction.json"
    extraction.write_text(
        json.dumps(
            {
                "programme": "Online MCA",
                "term": "Fall 2026",
                "status": "applicable",
                "notes": [],
                "exams": [
                    {
                        "course_code": "CS101",
                        "starts_at": "2026-11-29T14:00:00+05:30",
                        "ends_at": "2026-11-29T16:00:00+05:30",
                        "source_page": 2,
                        "source_text": "CS101 29 November 14:00",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    return [
        "--extraction", str(extraction),
        "--calendar", str(calendar),
        "--programme", "Online MCA",
        "--term", "Fall 2026",
    ], calendar


def test_preview_prints_evidence_without_exporting(inputs, capsys):
    args, calendar = inputs
    assert main(args) == 0
    assert "Evidence  Page 2" in capsys.readouterr().out
    assert sorted(path.name for path in calendar.parent.iterdir()) == [
        "exam.ics", "extraction.json"
    ]


@pytest.mark.parametrize("answer", ["", "n"])
def test_rejected_export_creates_no_file(inputs, tmp_path, monkeypatch, answer):
    args, _ = inputs
    output = tmp_path / "revised.ics"
    monkeypatch.setattr("builtins.input", lambda _: answer)
    assert main([*args, "--output", str(output)]) == 0
    assert not output.exists()


def test_approved_export_writes_revised_copy(inputs, tmp_path, monkeypatch):
    args, calendar = inputs
    original = calendar.read_bytes()
    output = tmp_path / "revised.ics"
    monkeypatch.setattr("builtins.input", lambda _: "yes")
    assert main([*args, "--output", str(output)]) == 0
    event = Calendar.from_ical(output.read_bytes()).walk("VEVENT")[0]
    assert event.decoded("DTSTART") == datetime(2026, 11, 29, 8, 30, tzinfo=UTC)
    assert calendar.read_bytes() == original


def test_export_cannot_overwrite_input(inputs):
    args, calendar = inputs
    original = calendar.read_bytes()
    assert main([*args, "--output", str(calendar)]) == 1
    assert calendar.read_bytes() == original
