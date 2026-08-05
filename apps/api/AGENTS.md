# Hello My Assistant API

Run all commands from `apps/api/`.

## Environment

### Prerequisites

- Python 3.14+
- uv

### Setup

- `uv sync` - Install dependencies and synchronize the virtual environment with `uv.lock`.

## Commands

- `uv run fastapi dev src/hello_my_assistant_api/main.py` - Run the API development server with automatic reload.
- `uv run ruff check --fix <file_path>` - Apply safe lint fixes to one file during development.
- `uv run ruff format <file_path>` - Format one file during development.
- `uv run ruff check src tests` - Verify all source and test files for lint violations without modifying them.
- `uv run ruff format --check src tests` - Verify the formatting of all source and test files without modifying them.
- `uv run mypy` - Run strict static type checking on the source package.
- `uv run mypy <file_path>` - Run static type checking on one file.

## Testing

- `uv run pytest -q` - Run the full test suite after completing a change.
- `uv run pytest tests/<test_file>.py -q` - Run one test file while developing.
- `uv run pytest tests/<test_file>.py::<test_name> -q` - Run the single test currently being implemented or fixed.
- `uv run pytest tests/<test_file>.py -v` - Display every test case, including parametrized cases.
- `uv run pytest tests/<test_file>.py::<test_name> -vv` - Investigate a failing test with detailed assertion output.
- `uv run python -m observability_e2e` - Explicitly validate the runtime observability contract against the configured model and Logfire; requires `LOGFIRE_READ_TOKEN` and is not part of the regular test suite.

## Boundaries

### Always do

- Use `uv run` to execute commands in the project environment.
- Add or update tests when changing observable behavior.
- Run the relevant tests first, then the full test suite after changing Python source code.
- Run Ruff and mypy before reporting Python source changes as complete.
- Keep configuration in environment variables rather than hard-coding environment-specific values.

### Ask first

Unless the current task explicitly requests it, ask before:

- Adding, removing, or upgrading dependencies.
- Changing the public API request or response contract.
- Adding, removing, or renaming environment variables.
- Changing default configuration values.
- Restructuring the source package or tests.

### Never do

- Commit `.env` files, API keys, or other secrets.
- Hard-code credentials or environment-specific service URLs.
- Call the real inference service from automated tests.
- Manually edit `.venv`, cache directories, or generated files.
- Weaken or remove tests, lint rules, or type checks merely to make verification pass.
