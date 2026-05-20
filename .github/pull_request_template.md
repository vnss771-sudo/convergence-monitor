## Summary

What changed?

## Validation

- [ ] `python -m app.cli validate-config`
- [ ] `python -m compileall -q app tests`
- [ ] `pytest -q`
- [ ] `ruff check .`

## Risk check

- [ ] Does not infer intent, coordination, causation, or inevitability.
- [ ] Does not add generated runtime artifacts to git.
- [ ] Does not change scoring semantics without tests.
- [ ] Does not add network-dependent tests to the default suite.
- [ ] Updates docs when CLI/operator behavior changes.

## Release impact

- [ ] No release impact.
- [ ] Requires release note.
- [ ] Requires migration note.
