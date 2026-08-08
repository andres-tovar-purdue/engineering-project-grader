import argparse
from pathlib import Path

from project_grader.project_inspection import inspect_project
from project_grader.project_manifest import write_project_manifest
from project_grader.spec_validation import validate_grading_spec


def main():
    parser = argparse.ArgumentParser(
        description="Engineering Project Grader"
    )

    subparsers = parser.add_subparsers(
        dest="command",
        required=True
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

    args = parser.parse_args()

    if args.command == "validate":
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