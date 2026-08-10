import argparse
from pathlib import Path

from project_grader.project_inspection import inspect_project
from project_grader.project_manifest import write_project_manifest
from project_grader.project_preparation import prepare_project
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
