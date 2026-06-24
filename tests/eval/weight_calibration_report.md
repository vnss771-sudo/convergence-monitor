# Weight calibration report

Deterministic grid search over `ScoringWeights`. This report is advisory:
weights change only via a governed PR (see docs/SCORING_GOVERNANCE.md).
Objective: maximise band agreement with the expert-labeled windows
(`tests/eval/labeled_windows.jsonl`), then separation between a high- and
low-activity window, staying monotonic in corroborating central documents.

Windows evaluated: 10.

| rank | central/doc | incid/doc | trust×  | div(2) | agreement | separation | monotonic | default |
|------|-------------|-----------|---------|--------|-----------|------------|-----------|---------|
| 1 | 0.75 | 0.1 | 0.75 | 1.25 | 0.9 | 7.5 | yes |  |
| 2 | 0.75 | 0.1 | 0.75 | 1.5 | 0.9 | 7.5 | yes |  |
| 3 | 0.75 | 0.15 | 0.75 | 1.25 | 0.9 | 7.5 | yes |  |
| 4 | 0.75 | 0.25 | 0.75 | 1.25 | 0.9 | 7.5 | yes |  |
| 5 | 0.5 | 0.1 | 0.75 | 1.25 | 0.9 | 7.1 | yes |  |
| 6 | 0.5 | 0.1 | 0.75 | 1.5 | 0.9 | 7.1 | yes |  |
| 7 | 0.5 | 0.1 | 0.75 | 1.75 | 0.9 | 7.1 | yes |  |
| 8 | 0.5 | 0.15 | 0.75 | 1.25 | 0.9 | 7.1 | yes |  |
| 9 | 0.5 | 0.15 | 0.75 | 1.5 | 0.9 | 7.1 | yes |  |
| 10 | 0.5 | 0.15 | 0.75 | 1.75 | 0.9 | 7.1 | yes |  |
| 11 | 0.5 | 0.25 | 0.75 | 1.25 | 0.9 | 7.1 | yes |  |
| 12 | 0.5 | 0.25 | 0.75 | 1.5 | 0.9 | 7.1 | yes |  |
| 13 | 0.5 | 0.25 | 0.75 | 1.75 | 0.9 | 7.1 | yes |  |
| 14 | 0.75 | 0.15 | 0.5 | 1.5 | 0.9 | 6.9 | yes | ★ |
| 15 | 0.75 | 0.1 | 0.5 | 1.25 | 0.9 | 6.9 | yes |  |

Default vector rank: **14 / 54** (agreement 0.9, separation 6.9).

Agreement is exact-band match against the expert windows. It is below 1.0
because the model is generous to thin/incidental evidence and the keyword
classifier under-counts paraphrased windows — the documented calibration
backlog (tests/eval/README.md). If a grid vector materially beats the default
on agreement without losing monotonicity, that is the signal to adopt it via a
governed scoring change.
