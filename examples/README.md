# Example project layout

`sample_project/` shows the directory convention used by the grader. Original
instructor materials belong in `project/` and datasets in `datasets/`.

After `prepare-project`, the instructor reviews the generated Markdown files in
`project/`, `rubric/`, and `reference/` before generating and approving a grading
specification.

`prepare-submissions` creates physical identity-redacted copies beneath
`grader/anonymized_submissions/Student_###/`. `grade-submissions` requires those
copies and an approved grading specification; it writes versioned preliminary
reports beneath `grader/grading_runs/`.
