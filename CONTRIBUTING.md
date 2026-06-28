# Contributing to config-map

Thanks for your interest! This is a small, focused tool — contributions should
keep it that way.

## Development setup

```bash
git clone https://github.com/toshon-jennings/config-map.git
cd config-map
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

## Running locally

```bash
# From the repo root:
python -m config_map

# Or after editable install:
config-map
```

## Project structure

```
config-map/
├── src/config_map/
│   ├── __init__.py        # Version string, public exports
│   └── __main__.py        # All logic: discovery, analysis, display
├── pyproject.toml         # Package metadata, dependencies, entry point
├── LICENSE
└── README.md
```

Everything is in one module by design. The tool does one thing and should stay
understandable in a single file.

## What to contribute

Good candidates:
- Support for new config formats (add to `KNOWN_CONFIGS` + an extractor)
- Bug fixes for edge cases in format detection
- Performance improvements for large directories
- Better skip heuristics for new tools' cache dirs

Not needed:
- Alternative output formats (CSV, JSON export) — that's a different tool
- Config file editing — that's a different tool
- GUI / TUI — the terminal table is the point

## Code style

- Match the existing structure (functions, not classes)
- No new dependencies without discussion (the only runtime dep is `rich`)
- Keep it Python 3.7+ compatible (no 3.10+ syntax)

## Submitting changes

1. Fork the repo
2. Create a feature branch (`git checkout -b my-fix`)
3. Make your change, test it locally
4. Bump the version in `pyproject.toml` and `src/config_map/__init__.py`
5. Push and open a PR

## Release process

Maintainers only:

```bash
# Bump version in pyproject.toml and __init__.py
python3 -m build
python3 -m twine upload dist/*
git tag v1.X.X
git push --tags
```
