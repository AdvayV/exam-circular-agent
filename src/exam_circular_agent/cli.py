"""Preview exam changes and export an approved calendar copy."""

import argparse
import sys
from contextlib import closing
from datetime import UTC, datetime
from functools import partial
from pathlib import Path

from icalendar import Calendar
from openai import OpenAI, OpenAIError
from pypdfium2 import PdfDocument, PdfiumError

from .agent import DEFAULT_MODEL, DEFAULT_PAGE_BUDGET, OpenAIPlanner, extract_schedule
from .calendar import Review, compare_schedule, revise_calendar
from .pdf import inspect_pdf_page
from .schedule import Schedule


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Review revised exam dates against a local exam calendar."
    )
    sources = parser.add_mutually_exclusive_group(required=True)
    sources.add_argument("--circular", type=Path, help="Read a PDF using the OpenAI API.")
    sources.add_argument(
        "--extraction", type=Path, help="Load an existing schedule JSON without calling a model."
    )
    parser.add_argument("--calendar", required=True, type=Path, help="Input exam calendar (.ics).")
    parser.add_argument("--programme", required=True, help="Student's programme, e.g. Online MCA.")
    parser.add_argument("--term", required=True, help="Academic term, e.g. Fall 2026.")
    parser.add_argument("--model", default=DEFAULT_MODEL, help=f"OpenAI model (default: {DEFAULT_MODEL}).")
    parser.add_argument(
        "--max-pages",
        type=int,
        default=DEFAULT_PAGE_BUDGET,
        help=f"Maximum number of PDF pages to inspect (default: {DEFAULT_PAGE_BUDGET}).",
    )
    parser.add_argument("--output", type=Path, help="Path for an approved revised calendar (.ics).")
    return parser


def _load_schedule(args: argparse.Namespace) -> Schedule:
    if args.extraction is not None:
        return Schedule.model_validate_json(args.extraction.read_bytes())

    with (
        OpenAI(timeout=60.0, max_retries=1) as client,
        closing(PdfDocument(args.circular)) as pdf,
    ):
        return extract_schedule(
            OpenAIPlanner(model=args.model, client=client),
            partial(inspect_pdf_page, pdf),
            programme=args.programme,
            term=args.term,
            page_count=len(pdf),
            max_pages=args.max_pages,
        )


def _show_review(review: Review) -> None:
    if not review.changes:
        print("No calendar changes proposed.")
    for change in review.changes:
        exam = change.exam
        zone = exam.starts_at.tzinfo
        print(change.summary)
        print(f"  Current   {change.old_start.astimezone(zone):%Y-%m-%d %H:%M %z}"
              f" to {change.old_end.astimezone(zone):%Y-%m-%d %H:%M %z}")
        print(f"  Proposed  {exam.starts_at:%Y-%m-%d %H:%M %z}"
              f" to {exam.ends_at:%Y-%m-%d %H:%M %z}")
        print(f"  Evidence  Page {exam.source_page} — {exam.source_text}")
    for note in review.notes:
        print(f"Note: {note}")


def main(argv: list[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    if not args.programme.strip() or not args.term.strip():
        parser.error("--programme and --term must be non-empty")
    if args.max_pages < 1:
        parser.error("--max-pages must be positive")

    try:
        calendar = Calendar.from_ical(args.calendar.read_bytes())
        if not isinstance(calendar, Calendar) or calendar.name != "VCALENDAR":
            raise ValueError("Expected a VCALENDAR file.")
        schedule = _load_schedule(args)
        review = compare_schedule(calendar, schedule, programme=args.programme, term=args.term)
        _show_review(review)
        if args.output is None or not review.changes:
            return 0

        if args.output.exists():
            raise FileExistsError(f"Output already exists: {args.output}")
        try:
            approved = input("Write these changes to a new calendar? [y/N] ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            approved = ""
        if approved not in {"y", "yes"}:
            print("Export cancelled.")
            return 0

        revised = revise_calendar(calendar, review, now=datetime.now(UTC)).to_ical()
        with args.output.open("xb") as output:
            output.write(revised)
        print(f"Wrote {args.output}")
        return 0
    except OpenAIError as exc:
        status = getattr(exc, "status_code", None)
        detail = f" (HTTP {status})" if status is not None else ""
        print(f"Model request failed{detail}. Check OPENAI_API_KEY and model access.", file=sys.stderr)
        return 1
    except (OSError, ValueError, PdfiumError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
