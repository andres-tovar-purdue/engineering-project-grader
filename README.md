# engineering-project-grader
Modular AI grading agent for engineering programming projects

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

The grader reads only the approved specification, sanitized manifest, and physical
anonymized copies. It sends one independent request per student, treats SLX files as
presence-only evidence, recalculates totals locally, and creates non-destructive
versioned output beneath `grader/grading_runs/run_v###/`:

- `grading_results.json` contains criterion-level evidence and preliminary scores.
- `preliminary_grading_report.csv` is the instructor-review worksheet.

The CSV leaves `total_instructor_score` blank. No final score or Brightspace update
is performed automatically.
