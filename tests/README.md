# Tests

Run the built-in unittest suite from the repository root:

```powershell
python -m unittest discover -s tests -v
```

OpenAI API calls and PDF reader behavior are mocked; the suite does not require an
API key or make network requests.

The suite also verifies that grading cannot read `student_map.json`, cannot fall
back to original Brightspace folders, structurally preflights SLX packages without
parsing or executing model internals, recalculates model
scores locally, and writes versioned reports with blank instructor scores.
