# Weight calibration report

Deterministic grid search over `ScoringWeights`. This report is advisory:
weights change only via a governed PR (see docs/SCORING_GOVERNANCE.md).
Objective: maximise separation between a high- and low-activity window while
staying monotonic in corroborating central documents.

| rank | central/doc | incid/doc | trust×  | div(2) | separation | monotonic | default |
|------|-------------|-----------|---------|--------|------------|-----------|---------|
| 1 | 0.75 | 0.1 | 0.75 | 1.25 | 6.1 | yes |  |
| 2 | 0.75 | 0.1 | 0.75 | 1.5 | 6.1 | yes |  |
| 3 | 0.75 | 0.1 | 0.75 | 1.75 | 6.1 | yes |  |
| 4 | 0.75 | 0.15 | 0.75 | 1.25 | 6.1 | yes |  |
| 5 | 0.75 | 0.15 | 0.75 | 1.5 | 6.1 | yes |  |
| 6 | 0.75 | 0.15 | 0.75 | 1.75 | 6.1 | yes |  |
| 7 | 0.75 | 0.25 | 0.75 | 1.25 | 6.1 | yes |  |
| 8 | 0.75 | 0.25 | 0.75 | 1.5 | 6.1 | yes |  |
| 9 | 0.75 | 0.25 | 0.75 | 1.75 | 6.1 | yes |  |
| 10 | 1.0 | 0.1 | 0.75 | 1.25 | 5.8 | yes |  |
| 11 | 1.0 | 0.1 | 0.75 | 1.5 | 5.8 | yes |  |
| 12 | 1.0 | 0.1 | 0.75 | 1.75 | 5.8 | yes |  |
| 13 | 1.0 | 0.15 | 0.75 | 1.25 | 5.8 | yes |  |
| 14 | 1.0 | 0.15 | 0.75 | 1.5 | 5.8 | yes |  |
| 15 | 1.0 | 0.15 | 0.75 | 1.75 | 5.8 | yes |  |

Default vector rank: **28 / 54**.

Note: windows here are synthetic representatives, not human-labeled ordinal
targets. Building `labeled_windows.jsonl` (expert band per real document set)
is the next step to turn this from a sensitivity tool into true calibration.
