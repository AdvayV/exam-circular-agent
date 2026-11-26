# Exam Circular Agent

[![Tests](https://github.com/AdvayV/exam-circular-agent/actions/workflows/tests.yml/badge.svg)](https://github.com/AdvayV/exam-circular-agent/actions/workflows/tests.yml)

Find out whether a revised exam circular affects your calendar. The agent reads
the circular, shows matching changes with page references, and exports a revised
calendar after you review it.

## Quick start

Use Python 3.11 or newer. From the project directory, create a virtual
environment with `python -m venv .venv` and activate it with
`source .venv/bin/activate` on macOS/Linux or `.\.venv\Scripts\Activate.ps1`
in PowerShell. Then install the app and run the synthetic example.

```sh
python -m pip install -e .
exam-circular-agent --extraction examples/demo-extraction.json --calendar examples/demo.ics --programme "Online MCA" --term "Fall 2026"
```

The saved extraction runs without an API key. It previews one change and
keeps `CS205` at its existing time.

```text
[CS101] Machine Learning Exam
  Current   2026-11-28 09:30 +0530 to 2026-11-28 11:30 +0530
  Proposed  2026-11-29 14:00 +0530 to 2026-11-29 16:00 +0530
  Evidence  Page 2 — CS101 | Machine Learning | 29 November 2026 | 14:00–16:00
```

## Read a PDF

Set `OPENAI_API_KEY` in your shell, then run the same example against its two-page
PDF.

```sh
exam-circular-agent --circular examples/demo.pdf --calendar examples/demo.ics --programme "Online MCA" --term "Fall 2026"
```

The agent starts on page one. It lets the model request another page and checks
that every cited page was inspected. Review the model's quoted row and extracted
times against the PDF before exporting. The CLI defaults to `gpt-6-luna` and a
five-page budget. Use `--model` with a model that supports image input and
structured outputs, or `--max-pages` to adjust the page budget.

In PDF mode, the selected page images and requested programme and term are
sent to OpenAI. Calendar matching runs locally and the calendar file is kept
on the device running the CLI. API calls use the API account associated with
your key. [OpenAI model options](https://developers.openai.com/api/docs/models)

## Review and export

Supply an exam-only `.ics` calendar with one timed event per course. The event
needs a unique `UID`, time zone-aware start and end, and a course code in
`X-COURSE-CODE` or at the start of its summary, such as `[CS101] Machine Learning
Exam`. The programme and term you give the CLI describe that calendar.

Add `--output revised.ics` to preview changes and prompt for approval. The
export writes a new file, preserves event IDs, and refuses to overwrite an
existing file. Review the source rows before importing the update. Repeated
course codes, recurring events, conflicting source dates, and courses without a
matching event appear as notes for manual review. This version updates existing
exam times only.

## Tests

```sh
python -m pip install -e ".[test]"
python -m pytest -q
```

The tests run offline on GitHub Actions for Windows and Ubuntu. They cover the
checked-in demo, page selection, evidence checks, programme mismatch, calendar
comparison, and approval before export. PDF-mode tests mock API requests.
