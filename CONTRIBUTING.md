# Contributing to OMRKit

Thank you for helping make **OMRKit** better! Contributions of all kinds — bug fixes, new optical sheet presets, detector improvements, Web Studio UX enhancements, and documentation — are warmly welcome.

## Development Setup

```bash
git clone https://github.com/duhanguler/omr.git
cd omr

# Python backend & SDK (Python 3.10+)
uv venv .venv
uv pip install --python .venv/bin/python -e ".[all,dev]"

# Optional: Web Studio frontend (Node 20+)
cd studio && npm ci && cd ..
```

## Quality Checks

Before opening a pull request, ensure all checks pass:

```bash
.venv/bin/ruff check src tests
.venv/bin/ruff format --check src tests
.venv/bin/mypy src/omrkit
.venv/bin/pytest -v --cov=omrkit

# If studio/ files changed:
cd studio && npm run build
```

## Privacy & Sample Images

Never commit real student personal data or raw smartphone images containing EXIF/GPS metadata. Always sanitize sample images first:

```bash
omrkit strip-exif path/to/raw_photos -o examples/my_sample/scans --max-dim 2200
```
