# Dependency policy

Runtime dependency declarations can use broad ranges during MVP development, but releases should include exact lock/constraints evidence.

## Policy

- No direct URL/path dependencies unless deliberately reviewed.
- No wildcard versions.
- Lower-bound-only specs are allowed during development but must be paired with generated release constraints.
- Pre-release dependencies must be intentional and documented.
- Release builds should produce an SBOM and checksum sidecars.

Run:

```bash
python tools/dependency_policy_audit.py --root "$PWD" --format markdown --fail-on high
```

The default failure level is `high`, so lower-bound-only dependencies are reported without blocking the release branch by default.
