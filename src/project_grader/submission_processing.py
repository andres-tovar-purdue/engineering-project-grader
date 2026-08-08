import json
import re
from datetime import datetime
from pathlib import Path


TEXT_EXTENSIONS = {
    ".py",
    ".m",
    ".txt",
    ".md",
    ".csv",
    ".json",
    ".ipynb",
    ".bas",
}

IMAGE_EXTENSIONS = {
    ".png",
    ".jpg",
    ".jpeg",
    ".webp",
}

MODEL_EXTENSIONS = {
    ".slx",
    ".mdl",
}

SPREADSHEET_EXTENSIONS = {
    ".xlsx",
    ".xlsm",
    ".xls",
}


def classify_file(path):
    """
    Classify a submitted file by extension.
    """

    extension = path.suffix.lower()

    if extension in TEXT_EXTENSIONS:
        return "text"

    if extension in IMAGE_EXTENSIONS:
        return "image"

    if extension in MODEL_EXTENSIONS:
        return "model"

    if extension in SPREADSHEET_EXTENSIONS:
        return "spreadsheet"

    return "other"


def read_text_file(path):
    """
    Read a text-based submission file.
    """

    return path.read_text(
        encoding="utf-8",
        errors="replace",
    )


def parse_brightspace_folder_name(folder_name):
    """
    Parse a Brightspace submission folder name.

    Example:
    100001-2000001 - astudent Avery Student - Jul 30, 2026 1053 PM

    Returns:
        {
            "username": "astudent",
            "full_name": "Avery Student",
            "submitted_at": datetime(...),
            "brightspace_prefix": "100001-2000001"
        }

    Returns None if the folder name does not match the expected format.
    """

    name = folder_name.strip()

    # Allow parsing of a ZIP filename as well as an extracted folder name.
    if name.lower().endswith(".zip"):
        name = name[:-4]

    parts = name.split(" - ")

    if len(parts) < 3:
        return None

    brightspace_prefix = parts[0].strip()
    identity = parts[1].strip()
    date_text = " - ".join(parts[2:]).strip()

    identity_parts = identity.split()

    if len(identity_parts) < 2:
        return None

    username = identity_parts[0]
    full_name = " ".join(identity_parts[1:])

    submitted_at = None

    date_formats = [
        "%b %d, %Y %I%M %p",
        "%b %d, %Y %I:%M %p",
    ]

    for date_format in date_formats:
        try:
            submitted_at = datetime.strptime(
                date_text,
                date_format,
            )
            break
        except ValueError:
            pass

    return {
        "username": username,
        "full_name": full_name,
        "submitted_at": submitted_at,
        "brightspace_prefix": brightspace_prefix,
    }


def inventory_submission_files(student_folder):
    """
    Inventory files contained in one Brightspace submission folder.
    """

    files = []

    for path in sorted(student_folder.rglob("*")):
        if not path.is_file():
            continue

        relative_path = path.relative_to(student_folder)
        file_type = classify_file(path)

        file_info = {
            "path": relative_path.as_posix(),
            "file_type": file_type,
            "extension": path.suffix.lower(),
            "size_bytes": path.stat().st_size,
        }

        if file_type == "text":
            file_info["content"] = read_text_file(path)

        files.append(file_info)

    return files


def process_submissions(project_path):
    """
    Parse Brightspace submission folders, group multiple attempts
    by Purdue username, select the latest submission, and assign
    anonymized student IDs.

    Returns:
        submissions:
            Agent-safe submission records using Student_### IDs.

        student_map:
            Local-only mapping containing username, full name,
            Brightspace folder names, and attempt metadata.
    """

    project_path = Path(project_path).resolve()
    submissions_path = project_path / "submissions"

    if not submissions_path.exists():
        raise FileNotFoundError(
            f"Submissions folder does not exist: "
            f"{submissions_path}"
        )

    submission_folders = sorted(
        path
        for path in submissions_path.iterdir()
        if path.is_dir()
    )

    grouped = {}
    unparsed_folders = []

    for folder in submission_folders:
        parsed = parse_brightspace_folder_name(
            folder.name
        )

        if parsed is None:
            unparsed_folders.append(folder.name)
            continue

        username = parsed["username"]

        attempt = {
            "folder": folder,
            "folder_name": folder.name,
            "full_name": parsed["full_name"],
            "submitted_at": parsed["submitted_at"],
            "brightspace_prefix": parsed["brightspace_prefix"],
        }

        grouped.setdefault(
            username,
            [],
        ).append(attempt)

    submissions = []
    student_map = {}

    # Sorting by username makes Student_001 assignments deterministic.
    for index, username in enumerate(
        sorted(grouped),
        start=1,
    ):
        student_id = f"Student_{index:03d}"

        attempts = grouped[username]

        # Sort attempts chronologically.
        attempts.sort(
            key=lambda attempt: (
                attempt["submitted_at"]
                or datetime.min
            )
        )

        selected_attempt = attempts[-1]

        files = inventory_submission_files(
            selected_attempt["folder"]
        )

        review_flags = []

        if len(attempts) > 1:
            review_flags.append(
                f"Multiple submissions detected: "
                f"{len(attempts)} attempts. "
                f"Latest attempt selected."
            )

        if selected_attempt["submitted_at"] is None:
            review_flags.append(
                "Submission timestamp could not be parsed."
            )

        # Agent-safe record.
        submissions.append(
            {
                "student_id": student_id,
                "attempt_count": len(attempts),
                "selected_attempt": len(attempts),
                "file_count": len(files),
                "files": files,
                "review_flags": review_flags,
            }
        )

        # Private local mapping.
        student_map[student_id] = {
            "username": username,
            "full_name": selected_attempt["full_name"],
            "selected_source_folder": (
                selected_attempt["folder_name"]
            ),
            "attempt_count": len(attempts),
            "attempts": [
                {
                    "source_folder": attempt["folder_name"],
                    "submitted_at": (
                        attempt["submitted_at"].isoformat()
                        if attempt["submitted_at"]
                        else None
                    ),
                }
                for attempt in attempts
            ],
        }

    return (
        submissions,
        student_map,
        unparsed_folders,
    )


def write_submission_manifest(project_path):
    """
    Process submissions and save:

    1. submission_manifest.json
       Safe for downstream AI grading.

    2. student_map.json
       Local-only identity mapping. Never send to the AI.
    """

    project_path = Path(project_path).resolve()

    (
        submissions,
        student_map,
        unparsed_folders,
    ) = process_submissions(project_path)

    grader_path = project_path / "grader"
    grader_path.mkdir(
        parents=True,
        exist_ok=True,
    )

    manifest_path = (
        grader_path
        / "submission_manifest.json"
    )

    map_path = (
        grader_path
        / "student_map.json"
    )

    manifest = {
        "manifest_version": "1.0",
        "submission_count": len(submissions),
        "unparsed_folder_count": len(
            unparsed_folders
        ),
        "unparsed_folders": unparsed_folders,
        "submissions": submissions,
    }

    with manifest_path.open(
        "w",
        encoding="utf-8",
    ) as file:
        json.dump(
            manifest,
            file,
            indent=2,
        )
        file.write("\n")

    with map_path.open(
        "w",
        encoding="utf-8",
    ) as file:
        json.dump(
            student_map,
            file,
            indent=2,
        )
        file.write("\n")

    return (
        manifest_path,
        map_path,
        manifest,
    )
