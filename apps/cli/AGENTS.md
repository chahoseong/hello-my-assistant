# Hello My Assistant CLI

Run all commands from `apps/cli/`.

## Environment

### Prerequisites

- Python 3.14+
- uv

### Setup

- `uv sync` - Install dependencies and synchronize the virtual environment with `uv.lock`.

## Commands

- `uv run python -m hello_my_assistant_cli.main` - Run the interactive CLI.
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

## Boundaries

### Always do

- Use `uv run` to execute commands in the project environment.
- Add or update tests when changing observable behavior.
- Run the relevant tests first, then the full test suite after changing Python source code.
- Run Ruff and mypy before reporting Python source changes as complete.
- Keep configurable API connection values in `Settings`.
- Use `pytest-httpx` to mock API requests in automated tests.

### Ask first

Unless the current task explicitly requests it, ask before:

- Adding, removing, or upgrading dependencies.
- Changing the API request or response contract used by the CLI.
- Changing user-facing prompts, output, or interactive commands.
- Adding, removing, or renaming environment variables.
- Changing default configuration values.
- Restructuring the source package or tests.

### Never do

- Commit `.env` files, API keys, or other secrets.
- Hard-code credentials or environment-specific API URLs outside `Settings`.
- Make real HTTP requests to the API from automated tests.
- Manually edit `.venv`, cache directories, or generated files.
- Weaken or remove tests, lint rules, or type checks merely to make verification pass.
