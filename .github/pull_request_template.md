## Summary
<!-- Briefly describe what this PR adds or fixes -->

## Checklist
- [ ] `ruff check src tests` and `ruff format --check src tests` pass
- [ ] `mypy src/omrkit` passes with zero errors
- [ ] `pytest` passes and new behavior is covered by tests
- [ ] Frontend builds cleanly (`cd studio && npm run build`) if Web Studio was touched
- [ ] Any sample images added have EXIF/GPS metadata stripped (`omrkit strip-exif`)
