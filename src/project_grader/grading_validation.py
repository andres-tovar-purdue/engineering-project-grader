import json
from pathlib import Path

from jsonschema import Draft202012Validator


def load_json(path):
    with Path(path).open("r", encoding="utf-8") as file:
        return json.load(file)


def validate_model_grading_response(response, schema_path):
    schema = load_json(schema_path)
    Draft202012Validator.check_schema(schema)
    errors = sorted(
        Draft202012Validator(schema).iter_errors(response),
        key=lambda error: list(error.absolute_path),
    )
    if errors:
        messages = []
        for error in errors:
            location = ".".join(str(item) for item in error.absolute_path)
            messages.append(f"{location or '<root>'}: {error.message}")
        raise ValueError("Invalid grading response:\n" + "\n".join(messages))


def calculate_grading_result(response, spec, submission):
    """Validate semantic references and calculate all totals locally."""
    if response["student_id"] != submission["student_id"]:
        raise ValueError("Grading response student_id does not match submission.")

    expected_criteria = {
        criterion["criterion_id"]: (task["task_id"], criterion)
        for task in spec["tasks"]
        for criterion in task["criteria"]
    }
    returned = {item["criterion_id"]: item for item in response["criteria"]}
    if len(returned) != len(response["criteria"]):
        raise ValueError("Grading response contains duplicate criterion IDs.")
    if set(returned) != set(expected_criteria):
        raise ValueError("Grading response criterion IDs do not match the spec.")

    feedback = {item["task_id"]: item["feedback"] for item in response["task_feedback"]}
    expected_tasks = {task["task_id"] for task in spec["tasks"]}
    if len(feedback) != len(response["task_feedback"]) or set(feedback) != expected_tasks:
        raise ValueError("Grading response task feedback does not match the spec.")

    artifact_paths = {file["path"] for file in submission["files"]}
    task_results = []
    all_review_reasons = list(submission.get("review_flags", []))
    all_review_reasons.extend(response["review_reasons"])
    any_review = bool(all_review_reasons) or response["review_required"]

    for task in spec["tasks"]:
        criterion_results = []
        task_score = 0.0
        for criterion in task["criteria"]:
            result = dict(returned[criterion["criterion_id"]])
            score = float(result["agent_score"])
            maximum = float(criterion["max_points"])
            if score > maximum:
                raise ValueError(
                    f"{criterion['criterion_id']} score exceeds max_points."
                )
            deduction_total = sum(
                float(item["points"]) for item in result["deductions"]
            )
            if abs((score + deduction_total) - maximum) > 1e-6:
                raise ValueError(
                    f"{criterion['criterion_id']} score plus deductions "
                    "does not equal max_points."
                )

            for evidence in result["evidence"]:
                path = evidence["artifact_path"]
                if path is not None and path not in artifact_paths:
                    raise ValueError(
                        f"Unknown evidence path for {criterion['criterion_id']}: {path}"
                    )
                if evidence["evidence_type"] == "unverifiable":
                    result["review_required"] = True
                    if not result["review_reasons"]:
                        result["review_reasons"] = [
                            "Required evidence could not be verified."
                        ]

            result["max_points"] = criterion["max_points"]
            result["deduction_total"] = round(deduction_total, 6)
            task_score += score
            if result["review_required"]:
                any_review = True
                all_review_reasons.extend(result["review_reasons"])
            criterion_results.append(result)

        if abs(task_score - sum(item["agent_score"] for item in criterion_results)) > 1e-6:
            raise ValueError(f"Local arithmetic failed for task {task['task_id']}.")
        task_results.append({
            "task_id": task["task_id"],
            "title": task["title"],
            "agent_score": round(task_score, 6),
            "max_points": task["max_points"],
            "feedback": feedback[task["task_id"]],
            "criteria": criterion_results,
        })

    total = round(sum(task["agent_score"] for task in task_results), 6)
    declared_total = float(spec["project"]["total_points"])
    if total < 0 or total > declared_total:
        raise ValueError("Calculated total is outside the project point range.")

    return {
        "student_id": submission["student_id"],
        "total_agent_score": total,
        "total_instructor_score": None,
        "project_total_points": spec["project"]["total_points"],
        "tasks": task_results,
        "review_required": any_review,
        "review_reasons": list(dict.fromkeys(all_review_reasons)),
    }
