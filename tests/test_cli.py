import json
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest
from icalendar import Calendar
from openai import OpenAI
from pypdfium2 import PdfDocument

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


def test_checked_in_demo_previews_only_changed_course(monkeypatch, capsys):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    examples = Path(__file__).resolve().parents[1] / "examples"
    args = [
        "--extraction", str(examples / "demo-extraction.json"),
        "--calendar", str(examples / "demo.ics"),
        "--programme", "Online MCA",
        "--term", "Fall 2026",
    ]
    assert main(args) == 0
    preview = capsys.readouterr().out
    assert "[CS101] Machine Learning Exam" in preview
    assert "2026-11-29 14:00 +0530" in preview
    assert "Evidence  Page 2" in preview
    assert "CS205" not in preview


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


def test_pdf_command_runs_the_page_loop_through_the_sdk(inputs, tmp_path, monkeypatch, capsys):
    args, _ = inputs
    pdf_path = tmp_path / "circular.pdf"
    with closing(PdfDocument.new()) as pdf:
        with closing(pdf.new_page(210, 300)), closing(pdf.new_page(210, 300)):
            pdf.save(pdf_path)

    schedule = json.loads(Path(args[1]).read_text(encoding="utf-8"))
    decisions = [
        {"page_to_inspect": 2, "schedule": None},
        {"page_to_inspect": None, "schedule": schedule},
    ]
    image_counts = []

    def respond(request):
        payload = json.loads(request.content)
        content = payload["input"][0]["content"]
        image_counts.append(sum(item["type"] == "input_image" for item in content))
        assert b"sample@example.invalid" not in request.content
        assert payload["text"]["format"]["type"] == "json_schema"
        assert payload["store"] is False
        decision = decisions.pop(0)
        return httpx.Response(
            200,
            json={
                "id": "resp_demo",
                "object": "response",
                "status": "completed",
                "output": [
                    {
                        "id": "msg_demo",
                        "type": "message",
                        "role": "assistant",
                        "status": "completed",
                        "content": [
                            {
                                "type": "output_text",
                                "text": json.dumps(decision),
                                "annotations": [],
                            }
                        ],
                    }
                ],
            },
        )

    def make_client(**kwargs):
        return OpenAI(
            api_key="test-key",
            http_client=httpx.Client(transport=httpx.MockTransport(respond)),
            **kwargs,
        )

    monkeypatch.setattr("exam_circular_agent.cli.OpenAI", make_client)
    assert main(["--circular", str(pdf_path), *args[2:]]) == 0
    assert image_counts == [1, 2]
    assert "Evidence  Page 2" in capsys.readouterr().out
