# Project Guidelines

## Project State
- Repository status: bootstrap phase (currently empty).
- Do not assume a language, framework, or package manager until project scaffolding is added.

## Build and Test
- No build, lint, or test commands are defined yet.
- After scaffolding, discover and use the project-native commands from config files (for example `package.json`, `pyproject.toml`, `Makefile`) and update this file.

## Architecture
- No architecture is defined yet.
- Once code exists, document high-level boundaries here and link deeper docs under `docs/` instead of duplicating content.

## Conventions
- Keep changes minimal and aligned with existing patterns once they exist.
- Prefer small, verifiable edits and run one-shot validation commands (no persistent watch/dev server processes for verification).
- If project-specific rules are added in `README.md` or `docs/`, link to them from here.
