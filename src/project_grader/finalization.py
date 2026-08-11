import csv
import json
import re
from pathlib import Path


FORBIDDEN_STUDENT_LANGUAGE = (
    "agent",
    "run_v",
    "confidence",
    "evidence_state",
    "evidence-state",
    "privacy flag",
    "instructor review",
    "internal validation",
    "anonymized",
)


def _safe_filename(value):
    return re.sub(r"[^A-Za-z0-9._-]+", "_", value).strip("_")


def _next_finalization_path(grader_path, run_version):
    root = grader_path / "finalizations" / run_version
    versions = []
    if root.is_dir():
        for path in root.iterdir():
            match = re.fullmatch(r"finalization_v(\d{3})", path.name)
            if path.is_dir() and match:
                versions.append(int(match.group(1)))
    return root / f"finalization_v{max(versions, default=0) + 1:03d}"


def _overall_feedback(tasks):
    strongest = max(tasks, key=lambda task: task["score"] / task["max_points"])
    focus = min(tasks, key=lambda task: task["score"] / task["max_points"])
    return (
        f"Your strongest work was in {strongest['title']}. "
        f"Continue developing the requirements described under {focus['title']}. "
        "The final grade reflects the completed technical work, required "
        "documentation, and submitted deliverables."
    )


def _validate_student_language(text):
    lowered = text.casefold()
    found = [term for term in FORBIDDEN_STUDENT_LANGUAGE if term in lowered]
    if found:
        raise ValueError(
            "Student-facing feedback contains internal grading language: "
            + ", ".join(found)
        )


def finalize_grading(
    project_path,
    run_version,
    approved_scores,
    criterion_overrides=None,
):
    """Create named final outputs without modifying an anonymous grading run."""
    project_path = Path(project_path).resolve()
    grader = project_path / "grader"
    run_path = grader / "grading_runs" / run_version
    run = json.loads((run_path / "grading_results.json").read_text(encoding="utf-8"))
    spec = json.loads((grader / "grading_spec_v001.json").read_text(encoding="utf-8"))
    student_map = json.loads((grader / "student_map.json").read_text(encoding="utf-8"))
    criterion_overrides = criterion_overrides or {}

    result_ids = {result["student_id"] for result in run["results"]}
    if result_ids != set(student_map) or result_ids != set(approved_scores):
        raise ValueError("Run results, student map, and approved scores do not align.")

    rows = []
    text_outputs = {}
    for result in run["results"]:
        student_id = result["student_id"]
        full_name = student_map[student_id]["full_name"]
        tasks = []
        for task in result["tasks"]:
            score = float(task["agent_score"])
            for criterion in task["criteria"]:
                key = (student_id, criterion["criterion_id"])
                if key in criterion_overrides:
                    score += (
                        float(criterion_overrides[key])
                        - float(criterion["agent_score"])
                    )
            tasks.append({
                "task_id": task["task_id"],
                "title": task["title"],
                "score": round(score, 6),
                "max_points": task["max_points"],
                "feedback": task["feedback"],
            })

        calculated_total = round(sum(task["score"] for task in tasks), 6)
        approved_total = float(approved_scores[student_id])
        if abs(calculated_total - approved_total) > 1e-6:
            raise ValueError(
                f"Task scores for {student_id} total {calculated_total}, "
                f"not approved score {approved_total}."
            )

        overall = _overall_feedback(tasks)
        student_text = [
            full_name,
            spec["project"]["title"],
            f"Final Grade: {approved_total:g}/100",
            "",
        ]
        for task in tasks:
            student_text.extend([
                f"{task['title']}: {task['score']:g}/{task['max_points']:g}",
                task["feedback"],
                "",
            ])
        student_text.extend([
            "Overall Feedback",
            overall,
            "",
            f"Final Grade: {approved_total:g}/100",
            "",
        ])
        rendered = "\n".join(student_text)
        _validate_student_language(rendered)
        filename = (
            f"{_safe_filename(full_name)}_Project_2_feedback.txt"
        )
        text_outputs[student_id] = (filename, rendered)

        row = {
            "actual_student_name": full_name,
            "anonymous_student_id": student_id,
            "preliminary_baseline_score": result["total_agent_score"],
            "final_instructor_score": approved_total,
            "overall_feedback": overall,
        }
        for index, task in enumerate(tasks, start=1):
            row[f"task_{index}_score"] = task["score"]
            row[f"task_{index}_feedback"] = task["feedback"]
        rows.append(row)

    output_path = _next_finalization_path(grader, run_version)
    output_path.mkdir(parents=True, exist_ok=False)
    csv_path = output_path / "Project_2_instructor_summary.csv"
    task_count = len(run["results"][0]["tasks"])
    fieldnames = [
        "actual_student_name",
        "anonymous_student_id",
        "preliminary_baseline_score",
        "final_instructor_score",
        *[
            item
            for index in range(1, task_count + 1)
            for item in (f"task_{index}_score", f"task_{index}_feedback")
        ],
        "overall_feedback",
    ]
    with csv_path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    txt_paths = []
    for student_id, (filename, rendered) in text_outputs.items():
        path = output_path / filename
        path.write_text(rendered, encoding="utf-8")
        txt_paths.append(path)

    validation = validate_finalization(
        output_path,
        rows,
        text_outputs,
        approved_scores,
    )
    return output_path, csv_path, txt_paths, validation


def validate_finalization(output_path, expected_rows, text_outputs, approved_scores):
    """Validate name mapping, arithmetic, file cardinality, and student language."""
    output_path = Path(output_path)
    csv_path = output_path / "Project_2_instructor_summary.csv"
    with csv_path.open("r", encoding="utf-8", newline="") as file:
        rows = list(csv.DictReader(file))
    if len(rows) != len(expected_rows):
        raise ValueError("Instructor summary row count is incorrect.")

    expected_by_id = {
        row["anonymous_student_id"]: row for row in expected_rows
    }
    for row in rows:
        student_id = row["anonymous_student_id"]
        expected = expected_by_id[student_id]
        if row["actual_student_name"] != expected["actual_student_name"]:
            raise ValueError(f"Name mapping failed for {student_id}.")
        task_scores = [
            float(value)
            for key, value in row.items()
            if re.fullmatch(r"task_\d+_score", key)
        ]
        final_score = float(row["final_instructor_score"])
        if abs(sum(task_scores) - final_score) > 1e-6:
            raise ValueError(f"Task arithmetic failed for {student_id}.")
        if abs(final_score - float(approved_scores[student_id])) > 1e-6:
            raise ValueError(f"CSV grade mismatch for {student_id}.")

    txt_paths = sorted(output_path.glob("*_Project_2_feedback.txt"))
    if len(txt_paths) != len(expected_rows):
        raise ValueError("Expected exactly one TXT file per student.")
    for student_id, (filename, _) in text_outputs.items():
        text = (output_path / filename).read_text(encoding="utf-8")
        _validate_student_language(text)
        final = float(approved_scores[student_id])
        marker = f"Final Grade: {final:g}/100"
        if text.count(marker) != 2:
            raise ValueError(f"TXT grade mismatch for {student_id}.")

    return {
        "names_mapped": True,
        "task_totals_match_final_scores": True,
        "one_txt_per_student": True,
        "csv_txt_grades_agree": True,
        "student_feedback_has_no_internal_language": True,
    }
