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
  -> prepare-submissions
```

`prepare-project` reads no student submissions and performs no grading. PDF support
extracts embedded text; scanned image-only PDFs require OCR before use. CSV files up
to 200 KB are supplied in full. Larger CSV files are limited to a labeled sample.
