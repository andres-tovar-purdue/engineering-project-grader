import base64
import csv
import io
import json
import mimetypes
import os
import re
from datetime import datetime
from pathlib import Path

from project_grader.ai_client import get_client
from project_grader.artifact_validation import preflight_slx_artifacts
from project_grader.grading_validation import (
    calculate_grading_result,
    validate_model_grading_response,
)
from project_grader.spec_validation import validate_grading_spec
from project_grader.rounding import DEFAULT_ROUNDING_POLICY, ROUNDING_POLICIES


GRADING_SPEC_FILENAME = "grading_spec_v001.json"
SUBMISSION_MANIFEST_FILENAME = "submission_manifest.json"
ANONYMIZED_FOLDER = "anonymized_submissions"
GRADING_RUNS_FOLDER = "grading_runs"
DEFAULT_GRADING_MODEL = "gpt-5.4-mini"
TEXT_EXTENSIONS = {".m", ".py", ".txt", ".md", ".csv", ".json", ".ipynb"}
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg"}
FORBIDDEN_MANIFEST_KEYS = {
    "username",
    "full_name",
    "selected_source_folder",
    "source_folder",
    "brightspace_prefix",
}


def parse_json_response(text):
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
        text = re.sub(r"\s*```$", "", text)
    return json.loads(text)


def _usage_value(value, key, default=None):
    if value is None:
        return default
    if isinstance(value, dict):
        return value.get(key, default)
    return getattr(value, key, default)


def extract_response_usage(response):
    """Normalize Responses API usage when the SDK returns it."""
    usage = _usage_value(response, "usage")
    if usage is None:
        return None
    input_details = _usage_value(usage, "input_tokens_details", {})
    output_details = _usage_value(usage, "output_tokens_details", {})
    return {
        "input_tokens": int(_usage_value(usage, "input_tokens", 0) or 0),
        "cached_input_tokens": int(
            _usage_value(input_details, "cached_tokens", 0) or 0
        ),
        "output_tokens": int(_usage_value(usage, "output_tokens", 0) or 0),
        "reasoning_tokens": int(
            _usage_value(output_details, "reasoning_tokens", 0) or 0
        ),
        "total_tokens": int(_usage_value(usage, "total_tokens", 0) or 0),
    }


def _find_forbidden_keys(value):
    found = set()
    if isinstance(value, dict):
        for key, item in value.items():
            if key.casefold() in FORBIDDEN_MANIFEST_KEYS:
                found.add(key)
            found.update(_find_forbidden_keys(item))
    elif isinstance(value, list):
        for item in value:
            found.update(_find_forbidden_keys(item))
    return found


def load_grading_inputs(project_path):
    """Load only the approved spec, sanitized manifest, and anonymized tree."""
    project_path = Path(project_path).resolve()
    grader_path = project_path / "grader"
    spec_path = grader_path / GRADING_SPEC_FILENAME
    manifest_path = grader_path / SUBMISSION_MANIFEST_FILENAME
    anonymized_root = grader_path / ANONYMIZED_FOLDER

    schema_path = (
        Path(__file__).resolve().parents[2]
        / "schemas"
        / "grading_spec.schema.json"
    )
    validate_grading_spec(spec_path, schema_path)
    with spec_path.open("r", encoding="utf-8") as file:
        spec = json.load(file)
    if spec.get("status") != "approved":
        raise RuntimeError(
            "grade-submissions requires an instructor-approved grading specification."
        )
    approval = spec.get("approval") or {}
    if not approval.get("approved_by") or not approval.get("approved_at"):
        raise RuntimeError("Approved grading specification lacks approval metadata.")

    with manifest_path.open("r", encoding="utf-8") as file:
        manifest = json.load(file)
    anonymization = manifest.get("anonymization") or {}
    if (
        manifest.get("manifest_version") != "2.0"
        or anonymization.get("status") != "validated"
        or anonymization.get("artifact_root") != "grader/anonymized_submissions"
        or anonymization.get("known_text_identities_redacted") is not True
    ):
        raise RuntimeError(
            "Submission manifest is not certified for anonymized AI grading. "
            "Run prepare-submissions first."
        )
    forbidden = _find_forbidden_keys(manifest)
    if forbidden:
        raise RuntimeError(
            "Submission manifest contains forbidden identity-bearing fields: "
            + ", ".join(sorted(forbidden))
        )
    if not anonymized_root.is_dir():
        raise FileNotFoundError(
            f"Anonymized submissions folder does not exist: {anonymized_root}"
        )

    expected_students = set()
    for submission in manifest.get("submissions", []):
        student_id = submission.get("student_id", "")
        if not re.fullmatch(r"Student_\d{3}", student_id):
            raise RuntimeError(f"Invalid anonymized student ID: {student_id}")
        expected_students.add(student_id)
        student_root = (anonymized_root / student_id).resolve()
        if not student_root.is_dir() or student_root.parent != anonymized_root.resolve():
            raise RuntimeError(f"Invalid anonymized student folder: {student_id}")

        seen_paths = set()
        for file_info in submission.get("files", []):
            relative_path = Path(file_info["path"])
            if (
                relative_path.is_absolute()
                or ".." in relative_path.parts
                or not relative_path.name.startswith("artifact_")
            ):
                raise RuntimeError(
                    f"Unsafe anonymized artifact path: {file_info['path']}"
                )
            artifact_path = (student_root / relative_path).resolve()
            if artifact_path.parent != student_root and student_root not in artifact_path.parents:
                raise RuntimeError(
                    f"Artifact escapes anonymized student folder: {file_info['path']}"
                )
            if not artifact_path.is_file():
                raise FileNotFoundError(
                    f"Anonymized artifact does not exist: {artifact_path}"
                )
            if file_info["path"] in seen_paths:
                raise RuntimeError("Duplicate anonymized artifact path in manifest.")
            seen_paths.add(file_info["path"])

    actual_students = {
        path.name for path in anonymized_root.iterdir() if path.is_dir()
    }
    if actual_students != expected_students:
        raise RuntimeError(
            "Anonymized student folders do not match submission manifest."
        )

    return spec_path, spec, manifest_path, manifest, anonymized_root


def build_student_input(spec, submission, student_root, instructions):
    """Build one multimodal request without parsing or executing SLX models."""
    content = []
    artifact_inventory = []
    text_sections = []
    image_limitations = []
    slx_preflight = preflight_slx_artifacts(submission, student_root)

    for file_info in submission["files"]:
        relative_path = file_info["path"]
        path = student_root / relative_path
        extension = path.suffix.lower()
        artifact_inventory.append({
            "path": relative_path,
            "file_type": file_info["file_type"],
            "extension": extension,
            "size_bytes": file_info["size_bytes"],
        })

        if extension in TEXT_EXTENSIONS:
            text = path.read_text(encoding="utf-8", errors="replace")
            if "content" in file_info and text != file_info["content"]:
                raise RuntimeError(
                    f"Anonymized text differs from manifest: {relative_path}"
                )
            text_sections.append(
                f"ARTIFACT: {relative_path}\nEVIDENCE TYPE: source_code\n{text}"
            )
        elif extension in IMAGE_EXTENSIONS:
            mime_type = mimetypes.guess_type(path.name)[0] or "image/png"
            encoded = base64.b64encode(path.read_bytes()).decode("ascii")
            content.append({
                "type": "input_text",
                "text": (
                    f"IMAGE ARTIFACT: {relative_path}. Treat only visible "
                    "content as image evidence. Flag suspected visible identity."
                ),
            })
            content.append({
                "type": "input_image",
                "image_url": f"data:{mime_type};base64,{encoded}",
                "detail": "auto",
            })
            image_limitations.append(relative_path)
        elif extension == ".slx":
            preflight = slx_preflight[relative_path]
            text_sections.append(
                f"ARTIFACT: {relative_path}\n"
                "EVIDENCE TYPE: structural_artifact_preflight\n"
                f"SLX PREFLIGHT: {json.dumps(preflight, sort_keys=True)}\n"
                "This preflight establishes artifact/container validity only. "
                "Do not infer model blocks, connections, parameters, settings, "
                "or behavior from the SLX package."
            )
        else:
            text_sections.append(
                f"ARTIFACT: {relative_path}\nEVIDENCE TYPE: file_presence\n"
                "Unsupported artifact; presence only was verified."
            )

    prompt = "\n\n".join([
        instructions,
        "APPROVED GRADING SPECIFICATION:\n" + json.dumps(spec, indent=2),
        "ANONYMIZED ARTIFACT INVENTORY:\n" + json.dumps(artifact_inventory, indent=2),
        "TEXT AND PRESENCE EVIDENCE:\n" + "\n\n---\n\n".join(text_sections),
        (
            "IMAGE PRIVACY LIMITATION:\nImage filenames and filesystem paths are "
            "anonymized, but image pixels were not redacted. If visible identity "
            "is suspected in any image, require instructor review. Images supplied: "
            + ", ".join(image_limitations)
        ),
        (
            "Return only one JSON object for student_id "
            f"{submission['student_id']} matching the required response schema."
        ),
    ])
    content.insert(0, {"type": "input_text", "text": prompt})
    return [{"role": "user", "content": content}]


def next_grading_run_path(grader_path):
    runs_path = grader_path / GRADING_RUNS_FOLDER
    existing_versions = []
    if runs_path.is_dir():
        for path in runs_path.iterdir():
            match = re.fullmatch(r"run_v(\d{3})", path.name)
            if path.is_dir() and match:
                existing_versions.append(int(match.group(1)))
    version = max(existing_versions, default=0) + 1
    return runs_path / f"run_v{version:03d}"


def render_preliminary_csv(results, spec):
    task_columns = [
        f"task_{index}_feedback"
        for index, _ in enumerate(spec["tasks"], start=1)
    ]
    fieldnames = [
        "student_id",
        "total_agent_score",
        "total_instructor_score",
        *task_columns,
        "review_required",
        "review_reasons",
    ]
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=fieldnames)
    writer.writeheader()
    for result in results:
        row = {
            "student_id": result["student_id"],
            "total_agent_score": result["total_agent_score"],
            "total_instructor_score": "",
            "review_required": str(result["review_required"]).lower(),
            "review_reasons": " | ".join(result["review_reasons"]),
        }
        for index, task in enumerate(result["tasks"], start=1):
            row[f"task_{index}_feedback"] = task["feedback"]
        writer.writerow(row)
    return stream.getvalue()


def grade_submissions(
    project_path,
    client=None,
    model=None,
    rounding_policy=DEFAULT_ROUNDING_POLICY,
):
    """Grade each anonymized submission independently and write a draft run."""
    project_path = Path(project_path).resolve()
    (
        spec_path,
        spec,
        manifest_path,
        manifest,
        anonymized_root,
    ) = load_grading_inputs(project_path)

    repository_root = Path(__file__).resolve().parents[2]
    response_schema_path = repository_root / "schemas" / "grading_result.schema.json"
    response_schema = json.loads(response_schema_path.read_text(encoding="utf-8"))
    instructions = (
        repository_root / "prompts" / "submission_grading_instructions.md"
    ).read_text(encoding="utf-8")

    client = client or get_client()
    selected_model = model or os.getenv("OPENAI_MODEL") or DEFAULT_GRADING_MODEL
    results = []
    per_student_usage = []

    for submission in manifest["submissions"]:
        student_root = anonymized_root / submission["student_id"]
        api_input = build_student_input(
            spec,
            submission,
            student_root,
            instructions,
        )
        response = client.responses.create(
            model=selected_model,
            instructions=(
                "You produce preliminary, evidence-based grading for instructor "
                "review. Never produce a final instructor grade."
            ),
            input=api_input,
            text={
                "format": {
                    "type": "json_schema",
                    "name": "preliminary_grading_response",
                    "schema": response_schema,
                    "strict": True,
                }
            },
            store=False,
        )
        if not response.output_text:
            raise RuntimeError(
                f"The model returned no grading result for {submission['student_id']}."
            )
        model_result = parse_json_response(response.output_text)
        validate_model_grading_response(model_result, response_schema_path)
        calculated = calculate_grading_result(
            model_result,
            spec,
            submission,
            rounding_policy=rounding_policy,
        )
        usage = extract_response_usage(response)
        calculated["api_usage"] = usage
        per_student_usage.append({
            "student_id": submission["student_id"],
            "available": usage is not None,
            **(usage or {}),
        })
        results.append(calculated)

    usage_fields = (
        "input_tokens",
        "cached_input_tokens",
        "output_tokens",
        "reasoning_tokens",
        "total_tokens",
    )
    usage_totals = {
        field: sum(item.get(field, 0) for item in per_student_usage)
        for field in usage_fields
    }

    run = {
        "run_version": None,
        "status": "preliminary_instructor_review_required",
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "model": selected_model,
        "rounding_policy": dict(ROUNDING_POLICIES[rounding_policy]),
        "api_usage": {
            "complete": all(item["available"] for item in per_student_usage),
            "per_student": per_student_usage,
            "totals": usage_totals,
        },
        "estimated_cost": None,
        "pricing_assumptions": None,
        "grading_spec": spec_path.name,
        "submission_manifest": manifest_path.name,
        "submission_count": len(results),
        "results": results,
    }

    run_path = next_grading_run_path(project_path / "grader")
    run["run_version"] = run_path.name.removeprefix("run_v")
    json_text = json.dumps(run, indent=2) + "\n"
    csv_text = render_preliminary_csv(results, spec)

    run_path.mkdir(parents=True, exist_ok=False)
    json_path = run_path / "grading_results.json"
    csv_path = run_path / "preliminary_grading_report.csv"
    json_path.write_text(json_text, encoding="utf-8")
    csv_path.write_text(csv_text, encoding="utf-8", newline="")

    return run_path, json_path, csv_path, run
