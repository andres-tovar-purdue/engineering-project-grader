# engineering-project-grader
Modular AI grading agent for engineering programming projects

The workflow has been validated through completed grading demonstrations for
MSPE 29800 Projects 2 and 3. It produces rubric-based preliminary assessments,
criterion-level evidence, task-by-task feedback, instructor-review artifacts,
and Brightspace-ready files. The instructor reviews and approves every final
grade, and submission to Brightspace remains a manual step.

Codex currently serves as the conversational coding and workflow-orchestration
interface. The grader application separately calls the OpenAI API to produce its
preliminary rubric-based assessments.

## Project preparation

Install the package in editable mode, place original PDF, Markdown, or plain-text
assignment materials in `PROJECT_PATH/project/`, and place CSV datasets in
`PROJECT_PATH/datasets/`. Then run:

```powershell
python -m project_grader prepare-project PROJECT_PATH
```

The command preserves original files and creates three drafts:

- `project/project_instructions.md`
- `rubric/instructor_rubric.md`
- `reference/reference_solution.md`

It refuses to overwrite any of these files. Review and edit all three drafts before
running `generate-spec`. The intended workflow is:

```text
prepare-project -> instructor review -> generate-spec -> approve-spec
  -> prepare-submissions -> grade-submissions -> instructor review
```

`prepare-project` reads no student submissions and performs no grading. PDF support
extracts embedded text; scanned image-only PDFs require OCR before use. CSV files up
to 200 KB are supplied in full. Larger CSV files are limited to a labeled sample.

## Submission preparation and grading

Prepare submissions before grading:

```powershell
python -m project_grader prepare-submissions PROJECT_PATH
```

This writes a sanitized `submission_manifest.json`, a private `student_map.json`,
and physical agent-facing copies beneath
`grader/anonymized_submissions/Student_###/`. Known usernames and student names are
redacted from text and filenames. Image pixels are not redacted and may still
require instructor review if visible identity is suspected.

After the grading specification is instructor-approved, run:

```powershell
python -m project_grader grade-submissions PROJECT_PATH
```

The default grading model is `gpt-5.4-mini`. Override it for one run with
`--model MODEL_ID`, or set `OPENAI_MODEL` for an environment-wide default.
New structured runs record the exact selected model and any token usage returned
by the Responses API. Cost remains unset unless maintainable pricing assumptions
are explicitly configured.

New grading runs default to the versioned `generous-v1` rounding policy. Criterion
scores remain exact. Each raw task subtotal is rounded upward to the next half point
without exceeding the task maximum; rounded task scores are summed and rounded
upward to the next whole point without exceeding the assignment maximum. Exact
half-points and whole numbers remain unchanged using a documented `1e-9`
floating-point tolerance. Use `--rounding-policy exact-v1` to disable rounding for
a run. Existing grading runs are never changed retroactively.

The grader reads only the approved specification, sanitized manifest, and physical
anonymized copies. It sends one independent request per student, structurally
preflights SLX containers without parsing or executing their models, uses required
PNGs for visible Simulink evidence, recalculates totals locally, and creates non-destructive
versioned output beneath `grader/grading_runs/run_v###/`:

- `grading_results.json` contains criterion-level evidence and preliminary scores.
- `preliminary_grading_report.csv` is the instructor-review worksheet.

The CSV leaves `total_instructor_score` blank. No final score or Brightspace update
is performed automatically.

## Current Limitations and Roadmap

The Project 2 and Project 3 demonstrations also identified areas for further
development. The following items are planned work, not descriptions of features
that are already complete:

1. Add deterministic notebook preprocessing and token estimation.
2. Detect duplicate, blank, corrupted, and low-information figures before grading.
3. Record complete API-attempt, retry, token-usage, and cost logs.
4. Strengthen structured-output validation and repair.
5. Build an evidence-centered interface for instructor review.
6. Formally support holistic instructor adjustments as records separate from
   rubric-based results.
7. Make workflow runs immutable and versioned while simplifying the current folder
   structure.
8. Improve Brightspace export and eventually support Brightspace API integration;
   submission remains manual today.
9. Add regression tests based on deidentified Project 2 and Project 3 cases.
