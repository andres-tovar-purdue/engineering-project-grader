# Tests

Run the built-in unittest suite from the repository root:

```powershell
python -m unittest discover -s tests -v
```

OpenAI API calls and PDF reader behavior are mocked; the suite does not require an
API key or make network requests.
