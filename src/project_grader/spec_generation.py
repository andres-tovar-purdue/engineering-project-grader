import json
import os
import re
from pathlib import Path

from project_grader.ai_client import get_client
from project_grader.project_manifest import build_project_manifest
from project_grader.spec_validation import validate_grading_spec


SOURCE_FOLDERS = {
    "project": "project_instructions",
    "rubric": "rubric",
    "reference": "reference_solution",
    "datasets": "dataset",
}

TEXT_EXTENSIONS = {
    ".txt",
    ".md",
    ".json",
    ".csv",
    ".py",
    ".m",
}


def make_source_id(relative_path):
    """
    Convert a relative file path into a stable source identifier.
    """

    source_id = relative_path.as_posix().lower()

    source_id = re.sub(
        r"[^a-z0-9]+",
        "_",
        source_id,
    )

    return source_id.strip("_")


def read_text_file(path):
    """
    Read a text-based project file.
    """

    return path.read_text(
        encoding="utf-8",
        errors="replace",
    )


def collect_project_sources(project_path):
    """
    Collect instructor-controlled source materials used to
    generate the grading specification.

    Student submissions and grader-generated files are
    intentionally excluded.
    """

    project_path = Path(project_path).resolve()

    sources = []

    for folder_name, source_type in SOURCE_FOLDERS.items():
        folder_path = project_path / folder_name

        if not folder_path.exists():
            continue

        for path in sorted(folder_path.rglob("*")):
            if not path.is_file():
                continue

            if path.suffix.lower() not in TEXT_EXTENSIONS:
                continue

            relative_path = path.relative_to(project_path)

            sources.append(
                {
                    "source_id": make_source_id(relative_path),
                    "source_type": source_type,
                    "path": relative_path.as_posix(),
                    "content": read_text_file(path),
                }
            )

    return sources


def build_generation_prompt(
    project_path,
    sources,
    schema,
):
    """
    Build the prompt used to generate a draft grading specification.
    """

    project_path = Path(project_path).resolve()

    source_sections = []

    for source in sources:
        source_sections.append(
            "\n".join(
                [
                    "----------------------------------------",
                    f"SOURCE ID: {source['source_id']}",
                    f"SOURCE TYPE: {source['source_type']}",
                    f"PATH: {source['path']}",
                    "CONTENT:",
                    source["content"],
                ]
            )
        )

    source_text = "\n\n".join(source_sections)

    schema_text = json.dumps(
        schema,
        indent=2,
    )

    prompt = f"""
Create a DRAFT project-specific grading specification for an
engineering computing assignment.

PROJECT FOLDER NAME:
{project_path.name}

IMPORTANT RULES:

1. Use only the supplied project materials as authoritative
   evidence about what students were asked to do.

2. Do not invent grading requirements.

3. The project instructions define the student requirements.

4. Instructor rubric/guidance may define grading policy and
   partial-credit rules.

5. A reference solution is evidence of one valid approach.
   Do not silently treat it as the only acceptable solution
   unless the published assignment requires that method.

6. If the materials are ambiguous, incomplete, contradictory,
   or do not define enough information for a defensible
   grading rule, record the issue in known_ambiguities.

7. Do not silently resolve ambiguities.

8. Where point allocations are not explicitly defined below
   the task level, you may propose a reasonable draft
   allocation, but identify that issue in known_ambiguities
   so the instructor can approve or revise it.

9. Set:
      schema_version = "1.0"
      spec_version = "0.1"
      status = "draft"

10. Use the exact SOURCE IDs supplied below when populating
    source_refs.

11. Criterion points must sum to their task max_points.

12. Task max_points must sum to the project total_points.

13. Include evidence requirements and review triggers when
    appropriate.

14. Preserve explicitly required methods, functions,
    software, filenames, variable ordering, plots, model
    structure, deliverables, and reproducibility requirements.

15. Allow technically valid alternatives when the published
    project does not prescribe a unique implementation.

16. Return ONLY a JSON object. Do not use Markdown fences,
    explanations, or commentary outside the JSON.

JSON SCHEMA:

{schema_text}

PROJECT MATERIALS:

{source_text}
"""

    return prompt.strip()


def parse_json_response(text):
    """
    Parse the model response as JSON.
    """

    text = text.strip()

    if text.startswith("```"):
        text = re.sub(
            r"^```(?:json)?\s*",
            "",
            text,
            flags=re.IGNORECASE,
        )

        text = re.sub(
            r"\s*```$",
            "",
            text,
        )

    return json.loads(text)


def generate_grading_spec(
    project_path,
    schema_path,
):
    """
    Generate, save, and validate a draft grading specification.
    """

    project_path = Path(project_path).resolve()
    schema_path = Path(schema_path).resolve()

    # Confirm that this is a recognizable project folder.
    build_project_manifest(project_path)

    sources = collect_project_sources(project_path)

    if not sources:
        raise RuntimeError(
            "No readable project materials were found. "
            "Add files to project, rubric, reference, "
            "or datasets."
        )

    with schema_path.open(
        "r",
        encoding="utf-8",
    ) as file:
        schema = json.load(file)

    prompt = build_generation_prompt(
        project_path,
        sources,
        schema,
    )

    client = get_client()

    model = os.getenv(
        "OPENAI_MODEL",
        "gpt-5",
    )

    response = client.responses.create(
        model=model,
        instructions=(
            "You are an instructor-supervised grading "
            "specification agent for engineering computing "
            "projects. Produce conservative, evidence-based "
            "draft grading specifications for instructor review."
        ),
        input=prompt,
        store=False,
    )

    if not response.output_text:
        raise RuntimeError(
            "The model returned no grading specification."
        )

    spec = parse_json_response(
        response.output_text
    )

    grader_path = project_path / "grader"
    grader_path.mkdir(
        parents=True,
        exist_ok=True,
    )

    output_path = (
        grader_path
        / "grading_spec_v001.json"
    )

    with output_path.open(
        "w",
        encoding="utf-8",
    ) as file:
        json.dump(
            spec,
            file,
            indent=2,
        )
        file.write("\n")

    # Validate the AI-generated file against
    # our stable local schema.
    validate_grading_spec(
        output_path,
        schema_path,
    )

    return output_path, spec