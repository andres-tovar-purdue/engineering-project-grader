import argparse
from pathlib import Path

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