# Guardrail language policy

Convergence Monitor reports observable public-document convergence. It must not claim hidden intent, coordination, causation, certainty, inevitability, or market prediction.

Preferred wording:

- "The score reports public-document convergence."
- "The evidence is drawn from configured public sources."
- "The system does not infer intent, coordination, causation, or future events."
- "The score is deterministic and rule-based."

Blocked or discouraged wording:

- Do not use hidden or secret intent claims.
- Do not claim the system proves motive, coordination, or causation.
- Do not write certain future-event claims.
- Do not use market trading or price-target framing.
- Do not write narrative claims that go beyond public-document evidence.

Run:

```bash
python tools/guardrail_language_audit.py --root "$PWD" --format markdown --fail-on error
```
