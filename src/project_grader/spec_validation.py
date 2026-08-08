import json
from pathlib import Path

from jsonschema import Draft202012Validator


def load_json(path):
    """Load and return a JSON file."""
    path = Path(path)

    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


def validate_grading_spec(spec_path, schema_path):
    """
    Validate a project-specific grading specification
    against the stable grading specification schema.
    """

    schema = load_json(schema_path)
    spec = load_json(spec_path)

    # Verify that our schema itself is valid.
    Draft202012Validator.check_schema(schema)

    # Validate the project-specific specification.
    validator = Draft202012Validator(schema)

    errors = sorted(
        validator.iter_errors(spec),
        key=lambda error: list(error.absolute_path),
    )

    if errors:
        messages = []

        for error in errors:
            location = ".".join(str(item) for item in error.absolute_path)

            if not location:
                location = "<root>"

            messages.append(
                f"{location}: {error.message}"
            )

        raise ValueError(
            "Invalid grading specification:\n"
            + "\n".join(messages)
        )

    return True