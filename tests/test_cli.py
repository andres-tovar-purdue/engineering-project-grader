import io
import unittest
from pathlib import Path
from unittest.mock import patch

from project_grader.cli import main


class CliTests(unittest.TestCase):
    @patch("project_grader.cli.prepare_project")
    @patch("sys.argv", ["project_grader", "prepare-project", "demo"])
    def test_prepare_project_command(self, prepare):
        prepare.return_value = {
            "output_paths": {
                "project_instructions": Path("project/project_instructions.md"),
                "instructor_rubric": Path("rubric/instructor_rubric.md"),
                "reference_solution": Path("reference/reference_solution.md"),
            },
            "limitations": [],
        }
        output = io.StringIO()

        with patch("sys.stdout", output):
            main()

        prepare.assert_called_once_with("demo")
        self.assertIn("Instructor review is required", output.getvalue())

    @patch("project_grader.cli.grade_submissions")
    @patch("sys.argv", ["project_grader", "grade-submissions", "demo"])
    def test_grade_submissions_command(self, grade):
        grade.return_value = (
            Path("grader/grading_runs/run_v001"),
            Path("grader/grading_runs/run_v001/grading_results.json"),
            Path("grader/grading_runs/run_v001/preliminary_grading_report.csv"),
            {"submission_count": 2},
        )
        output = io.StringIO()

        with patch("sys.stdout", output):
            main()

        grade.assert_called_once_with("demo")
        self.assertIn("Final instructor scores were not assigned", output.getvalue())


if __name__ == "__main__":
    unittest.main()
