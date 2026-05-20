# Security Policy

## Supported versions

The active `main` branch and the latest release tag are supported.

## Reporting a vulnerability

Open a private security advisory on GitHub, or contact the repository owner through GitHub.

Do not open public issues for suspected vulnerabilities involving:

- leaked credentials
- unsafe source ingestion behavior
- arbitrary file writes
- CI token exposure
- dependency compromise
- malicious feed or document payload handling

## Security boundaries

Convergence Monitor reads public documents and produces deterministic convergence evidence summaries. It must not:

- execute fetched document content
- infer intent, causation, coordination, or inevitability
- store secrets in tracked files
- ship runtime evidence archives inside source releases
- allow generated artifacts to affect deterministic tests unless explicitly fixture-scoped

## Operator requirements

- Run live ingestion from a low-privilege environment.
- Keep API keys and tokens out of repo files.
- Prefer release tags or full commit SHAs for packaging.
- Review generated evidence before publication.
