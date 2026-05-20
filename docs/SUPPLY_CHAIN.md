# Supply-chain integrity

Phase 3 moves the project from "tests pass" to "release evidence is inspectable."

## Local guarantees

The local tools provide:

- Dependency policy findings from `pyproject.toml`.
- Minimal CycloneDX-style SBOM generation.
- Artifact SHA-256 sidecars.
- Provenance JSON tying artifacts to git commit, tag, runner, and builder environment.
- Verification that SBOM, provenance, and checksum files agree.

## CI guarantees

The workflow templates add:

- Guardrail-language audit on pull requests.
- Dependency review on pull requests.
- SBOM artifact upload on push/PR/manual runs.
- Signed GitHub artifact attestations for tagged releases.

## Release rule

A release is not complete unless the following exist together:

- Source distribution or source zip.
- Wheel when packaging is enabled.
- `convergence-monitor.sbom.cdx.json`.
- `release-provenance.json`.
- `.sha256` sidecars for each artifact.
- GitHub artifact attestation for tagged release artifacts.
