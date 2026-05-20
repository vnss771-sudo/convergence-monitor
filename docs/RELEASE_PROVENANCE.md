# Release provenance

`tools/generate_release_provenance.py` writes `dist/release-provenance.json`.

It records:

- Git commit, branch, tag, and remote.
- Dirty-tree status.
- Python version and platform.
- GitHub Actions run metadata when available.
- Artifact names, sizes, and SHA-256 digests.
- Release checks performed before artifact generation.

This file is useful but not a signature. Tagged releases should also use GitHub artifact attestations through `.github/workflows/release-provenance.yml`.
