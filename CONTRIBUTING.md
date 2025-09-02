# Contributing to analyze-qna

Thanks for your interest in contributing! This project welcomes issues and pull requests.

## Getting Started

1. Fork the repo and clone your fork
2. Create a feature branch: `git checkout -b feat/your-change`
3. Set up dev environment:
   - `python -m venv .venv && source .venv/bin/activate`
   - `pip install -r requirements.txt`
4. Run locally:
   - `python src/analyze_qna.py --file path/to/qna.yaml`
   - Or via Node wrapper: `node bin/analyze-qna.js --file path/to/qna.yaml`

## Development Guidelines

- Keep files under ~512 lines when practical; extract utilities if needed
- Prefer clear, readable code; meaningful names; early returns; minimal nesting
- Avoid adding heavy dependencies; keep `requirements.txt` lean
- Optional imports (e.g., `mistral-common`) should fail gracefully
- Write explicit error messages that aid debugging

## Submitting Changes

1. Lint/type check locally if you use mypy/ruff
2. Commit with clear messages: `feat:`, `fix:`, `docs:`, `refactor:`, etc.
3. Open a Pull Request against `main`, describing the change and rationale
4. Link any related issues

## Reporting Issues

- Provide steps to reproduce, expected vs. actual behavior
- Include sample `qna.yaml` if relevant (redact sensitive data)

## Contact

Maintainer: Wes Jackson (`wjackson@redhat.com`)

Thanks again for contributing!
