import argparse
import json
from pathlib import Path

from project_grader.project_inspection import inspect_project
from project_grader.project_manifest import write_project_manifest
from project_grader.project_preparation import prepare_project
from project_grader.grading import grade_submissions
from project_grader.finalization import finalize_grading
from project_grader.rounding import DEFAULT_ROUNDING_POLICY, ROUNDING_POLICIES
from project_grader.spec_validation import validate_grading_spec
from project_grader.spec_generation import generate_grading_spec
from project_grader.submission_processing import write_submission_manifest

import os

from dotenv import load_dotenv
from project_grader.spec_approval import approve_grading_spec

load_dotenv()

def main():
    parser = argparse.ArgumentParser(
        description="Engineering Project Grader"
    )

    subparsers = parser.add_subparsers(
        dest="command",
        required=True
    )

    # prepare-project command
    prepare_project_parser = subparsers.add_parser(
        "prepare-project",
        help="Create instructor-reviewable project preparation drafts."
    )

    prepare_project_parser.add_argument(
        "project_path",
        help="Path to the project folder."
    )

    # validate command
    validate_parser = subparsers.add_parser(
        "validate",
        help="Validate a grading specification."
    )

    validate_parser.add_argument(
        "spec_path",
        help="Path to the project-specific grading specification."
    )

    # inspect command
    inspect_parser = subparsers.add_parser(
        "inspect",
        help="Inspect a grading project folder."
    )

    inspect_parser.add_argument(
        "project_path",
        help="Path to the project folder."
    )

    # manifest command
    manifest_parser = subparsers.add_parser(
        "manifest",
        help="Create a machine-readable project manifest."
    )

    manifest_parser.add_argument(
        "project_path",
        help="Path to the project folder."
    )

    # generate-spec command
    generate_spec_parser = subparsers.add_parser(
        "generate-spec",
        help="Generate a draft project-specific grading specification."
    )

    generate_spec_parser.add_argument(
        "project_path",
        help="Path to the project folder."
    )

    # approve-spec command
    approve_spec_parser = subparsers.add_parser(
        "approve-spec",
        help="Approve an instructor-reviewed grading specification."
    )

    approve_spec_parser.add_argument(
        "spec_path",
        help="Path to the draft grading specification."
    )

    approve_spec_parser.add_argument(
        "--allow-unresolved",
        action="store_true",
        help="Allow approval even when unresolved ambiguities remain."
    )

    # prepare-submissions command
    prepare_parser = subparsers.add_parser(
        "prepare-submissions",
        help="Prepare and anonymize student submissions."
    )

    prepare_parser.add_argument(
        "project_path",
        help="Path to the project folder."
    )

    # grade-submissions command
    grade_parser = subparsers.add_parser(
        "grade-submissions",
        help="Create preliminary grading reports for anonymized submissions."
    )

    grade_parser.add_argument(
        "project_path",
        help="Path to the project folder."
    )

    finalize_parser = subparsers.add_parser(
        "finalize-grading",
        help="Create offline instructor and student-facing final reports.",
    )
    finalize_parser.add_argument("project_path", help="Path to the project folder.")
    finalize_parser.add_argument("--run", required=True, help="Baseline run version.")
    finalize_parser.add_argument(
        "--score",
        action="append",
        required=True,
        help="Approved score as Student_###=POINTS.",
    )
    finalize_parser.add_argument(
        "--criterion-score",
        action="append",
        default=[],
        help="Criterion override as Student_###:CRITERION_ID=POINTS.",
    )
    grade_parser.add_argument(
        "--model",
        help=(
            "Responses API model override. Defaults to OPENAI_MODEL when set, "
            "otherwise gpt-5.4-mini."
        ),
    )
    grade_parser.add_argument(
        "--rounding-policy",
        choices=sorted(ROUNDING_POLICIES),
        default=DEFAULT_ROUNDING_POLICY,
        help="Task/project rounding policy for new preliminary grades.",
    )

    args = parser.parse_args()

    if args.command == "prepare-project":
        result = prepare_project(args.project_path)

        print("Draft project preparation artifacts written:")
        for path in result["output_paths"].values():
            print(f"  - {path}")

        if result["limitations"]:
            print("\nDataset limitations:")
            for limitation in result["limitations"]:
                print(f"  - {limitation}")

        print(
            "\nInstructor review is required before running generate-spec."
        )

    elif args.command == "validate":
        schema_path = (
            Path(__file__).resolve().parents[2]
            / "schemas"
            / "grading_spec.schema.json"
        )

        validate_grading_spec(
            args.spec_path,
            schema_path
        )

        print("Grading specification is valid.")

    elif args.command == "inspect":
        summary = inspect_project(args.project_path)

        print(f"Project: {summary['project_path']}")
        print()

        for folder_name, info in summary["folders"].items():
            if info["exists"]:
                print(
                    f"{folder_name}: "
                    f"{info['file_count']} file(s)"
                )

                for file_path in info["files"]:
                    print(f"  - {file_path}")

            else:
                print(f"{folder_name}: MISSING")

        print()
        print("Project inspection complete.")

    elif args.command == "manifest":
        output_path, manifest = write_project_manifest(
            args.project_path
        )

        print(f"Project manifest written to: {output_path}")
        print(f"Files inventoried: {manifest['total_files']}")
        print(
            f"Submission folders: "
            f"{manifest['submission_count']}"
        )

    elif args.command == "generate-spec":
        schema_path = (
            Path(__file__).resolve().parents[2]
            / "schemas"
            / "grading_spec.schema.json"
        )

        output_path, spec = generate_grading_spec(
            args.project_path,
            schema_path,
        )

        print(
            f"Draft grading specification written to: "
            f"{output_path}"
        )

        print(
            f"Tasks generated: "
            f"{len(spec['tasks'])}"
        )

        print(
            "Grading specification passed schema validation."
        )

    elif args.command == "approve-spec":
        schema_path = (
            Path(__file__).resolve().parents[2]
            / "schemas"
            / "grading_spec.schema.json"
        )

        approved_by = os.getenv(
            "GRADER_INSTRUCTOR_NAME"
        )

        if not approved_by:
            raise RuntimeError(
                "GRADER_INSTRUCTOR_NAME was not found. "
                "Add it to the local .env file."
            )

        output_path, spec, unresolved = approve_grading_spec(
            args.spec_path,
            schema_path,
            approved_by=approved_by,
            allow_unresolved=args.allow_unresolved,
        )

        print(
            f"Grading specification approved: "
            f"{output_path}"
        )

        print(
            f"Approved by: "
            f"{spec['approval']['approved_by']}"
        )

        if unresolved:
            print(
                f"Warning: approved with "
                f"{len(unresolved)} unresolved ambiguity/ambiguities."
            )

    elif args.command == "prepare-submissions":
        manifest_path, map_path, manifest = (
            write_submission_manifest(
                args.project_path
            )
        )

        print(
            f"Submission manifest written to: "
            f"{manifest_path}"
        )

        print(
            f"Student map written to: "
            f"{map_path}"
        )

        print(
            f"Submissions found: "
            f"{manifest['submission_count']}"
        )

        print(
            "Anonymized artifacts written beneath: "
            f"{Path(args.project_path).resolve() / 'grader' / 'anonymized_submissions'}"
        )

    elif args.command == "grade-submissions":
        run_path, json_path, csv_path, run = grade_submissions(
            args.project_path,
            model=args.model,
            rounding_policy=args.rounding_policy,
        )

        print(f"Preliminary grading run written to: {run_path}")
        print(f"Structured results: {json_path}")
        print(f"Instructor review report: {csv_path}")
        print(f"Submissions graded: {run['submission_count']}")
        print("Final instructor scores were not assigned.")

    elif args.command == "finalize-grading":
        approved_scores = {}
        for item in args.score:
            student_id, score = item.split("=", 1)
            approved_scores[student_id] = float(score)
        overrides = {}
        for item in args.criterion_score:
            key, score = item.split("=", 1)
            student_id, criterion_id = key.split(":", 1)
            overrides[(student_id, criterion_id)] = float(score)
        output_path, csv_path, txt_paths, validation = finalize_grading(
            args.project_path,
            args.run,
            approved_scores,
            overrides,
        )
        print(f"Finalization written to: {output_path}")
        print(f"Instructor summary: {csv_path}")
        for path in txt_paths:
            print(f"Student feedback: {path}")
        print(f"Offline validation: {json.dumps(validation, sort_keys=True)}")
