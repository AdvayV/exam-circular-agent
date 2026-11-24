from base64 import b64decode
from contextlib import closing
from datetime import UTC, datetime
from io import BytesIO

import pytest
from PIL import Image
from pypdfium2 import PdfDocument

from exam_circular_agent.agent import AgentError, Decision, OpenAIPlanner, Page, extract_schedule
from exam_circular_agent.pdf import inspect_pdf_page
from exam_circular_agent.schedule import Exam, Schedule


def sample_schedule(source_page):
    exam = Exam(
        course_code="CS101",
        starts_at=datetime(2026, 11, 29, 8, 30, tzinfo=UTC),
        ends_at=datetime(2026, 11, 29, 10, 30, tzinfo=UTC),
        source_page=source_page,
        source_text="CS101 — 29 November, 14:00",
    )
    return Schedule(
        status="applicable", programme="Online MCA", term="Fall 2026", exams=(exam,), notes=()
    )


def run(decide, inspected, max_pages=5):
    def inspect_page(number):
        inspected.append(number)
        return Page(number, "data:image/png;base64,stub")

    return extract_schedule(
        decide,
        inspect_page,
        programme="Online MCA",
        term="Fall 2026",
        page_count=4,
        max_pages=max_pages,
    )


def test_model_can_choose_a_nonconsecutive_page():
    def decide(programme, term, page_count, remaining, pages):
        assert programme == "Online MCA"
        assert term == "Fall 2026"
        assert page_count == 4
        if remaining == 3:
            return Decision(page_to_inspect=3, schedule=None)
        assert [page.number for page in pages] == [1, 3]
        return Decision(page_to_inspect=None, schedule=sample_schedule(3))

    inspected = []
    result = run(decide, inspected)
    assert inspected == [1, 3]
    assert result.exams[0].source_page == 3


def test_evidence_must_come_from_an_inspected_page():
    with pytest.raises(AgentError, match="did not inspect"):
        run(lambda *_: Decision(page_to_inspect=None, schedule=sample_schedule(3)), [])


@pytest.mark.parametrize(("requested", "budget", "error"), [(1, 5, "already"), (2, 1, "budget")])
def test_invalid_page_requests_are_bounded(requested, budget, error):
    inspected = []
    with pytest.raises(AgentError, match=error):
        run(lambda *_: Decision(page_to_inspect=requested, schedule=None), inspected, budget)
    assert inspected == [1]


def test_pdf_inspection_returns_an_image_for_the_requested_page():
    with closing(PdfDocument.new()) as pdf:
        with closing(pdf.new_page(210, 300)), closing(pdf.new_page(300, 210)):
            result = inspect_pdf_page(pdf, 2)
    assert result.number == 2
    with Image.open(BytesIO(b64decode(result.image_url.split(",", maxsplit=1)[1]))) as image:
        assert image.format == "PNG"
        assert image.width > image.height


def test_openai_receives_only_scope_and_numbered_page_images(monkeypatch):
    from openai import OpenAI

    expected = Decision(page_to_inspect=None, schedule=sample_schedule(1))

    def parse(**request):
        assert request["store"] is False
        assert request["text_format"] is Decision
        content = request["input"][0]["content"]
        assert "Online MCA" in content[0]["text"]
        assert content[1]["text"] == "Circular page 1"
        assert content[2]["image_url"] == "data:image/png;base64,stub"
        return type("Response", (), {"output_parsed": expected})()

    with OpenAI(api_key="test-key") as client:
        monkeypatch.setattr(client.responses, "parse", parse)
        result = OpenAIPlanner(client=client)(
            "Online MCA", "Fall 2026", 1, 0, (Page(1, "data:image/png;base64,stub"),)
        )
    assert result == expected
