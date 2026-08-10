import unittest

from project_grader.grading_validation import calculate_grading_result


class GradingValidationTests(unittest.TestCase):
    def test_rejects_model_arithmetic(self):
        spec = {
            "project": {"total_points": 1},
            "tasks": [{
                "task_id": "T1",
                "title": "Task",
                "max_points": 1,
                "criteria": [{"criterion_id": "C1", "max_points": 1}],
            }],
        }
        submission = {"student_id": "Student_001", "files": [], "review_flags": []}
        response = {
            "student_id": "Student_001",
            "criteria": [{
                "criterion_id": "C1",
                "agent_score": 0.5,
                "deductions": [],
                "justification": "Partial evidence.",
                "evidence": [],
                "confidence": "medium",
                "review_required": False,
                "review_reasons": [],
            }],
            "task_feedback": [{"task_id": "T1", "feedback": "Review."}],
            "review_required": False,
            "review_reasons": [],
        }

        with self.assertRaisesRegex(ValueError, "score plus deductions"):
            calculate_grading_result(response, spec, submission)


if __name__ == "__main__":
    unittest.main()
