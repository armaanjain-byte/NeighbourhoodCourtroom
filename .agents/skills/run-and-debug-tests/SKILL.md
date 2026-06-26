---
name: run-and-debug-tests
description: Use when the user asks to run unit tests, execute pytest, debug a failing test case, check test coverage, or troubleshoot test environment issues in this repository.
---

# Running and Debugging Tests in NeighbourhoodCourtroom

This guide provides instructions for correctly running the automated test suite and troubleshooting common failure patterns encountered in this repository's history.

## 1. Running the Test Suite

The test suite is built on `pytest`. In Windows/PowerShell environments, running `pytest` directly may result in `CommandNotFoundException` if the virtual environment's Scripts directory is not in PATH.

**Always use the following exact command:**
```bash
python -m pytest
```
*(or `python3 -m pytest` depending on the local alias).*

### Running Specific Test Files or Targets
- **Single file**: `python -m pytest tests/test_llm_provider.py`
- **Specific test method**: `python -m pytest tests/test_llm_provider.py::TestGeminiProvider::test_gemini_rest_chat_function_response_role`

## 2. Interpreting Coverage Output

`pytest` is configured with `pytest-cov` to automatically report test coverage upon completion.
- **Coverage Goal**: Maintain high coverage across core modules (`agents/`, `engine/`, `llm/`, `models/`).
- **Exemptions**: Scripts in `scripts/` and `app.py` represent entrypoints or live verification tools and are expected to show lower unit test coverage; they are verified via integration or live testing instead.

## 3. Common Failure Patterns & Troubleshooting

### A. Stale Imports or Missing Modules
- **Symptom**: `ModuleNotFoundError: No module named 'google.genai'` or similar.
- **Cause/Fix**: The project migrated from the `google-genai` SDK to direct REST API calls using `requests`. Ensure your virtual environment matches `requirements.txt` (`requests>=2.31.0,<3.0.0`). Do not import `google.genai` in tests or application code.

### B. Pytest Configuration Conflicts
- **Symptom**: Unrecognized arguments or plugin load errors.
- **Cause/Fix**: Ensure `pytest-cov` is installed. If running in an environment where coverage tracking conflicts with a debugger (e.g., IDE debugging sessions), pass `--no-cov` to disable coverage tracking: `python -m pytest --no-cov`.

### C. Post-Request Mutation in Mocks
- **Symptom**: Mocking `requests.post` and inspecting `call_args.kwargs['json']` shows unexpected data (e.g., `role: "model"` instead of `role: "user"`).
- **Cause/Fix**: If payload dictionaries or lists are passed by reference, subsequent code (like appending the model's response to chat history) will mutate the mock's recorded arguments. Ensure application code passes copies (e.g., `list(self.contents)`) to avoid mock verification artifacts.
