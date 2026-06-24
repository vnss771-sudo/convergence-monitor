# Weight calibration report

Deterministic grid search over `ScoringWeights`. This report is advisory:
weights change only via a governed PR (see docs/SCORING_GOVERNANCE.md).
Objective: maximise band agreement with the expert-labeled windows
(`tests/eval/labeled_windows.jsonl`), then separation between a high- and
low-activity window, staying monotonic in corroborating central documents.

Windows evaluated: 10.

| rank | central/doc | incid/doc | trust×  | div(2) | agreement | separation | monotonic | default |
|------|-------------|-----------|---------|--------|-----------|------------|-----------|---------|
| 1 | 0.75 | 0.15 | 0.5 | 1.5 | 0.7 | 5.6 | yes | ★ |
| 2 | 0.75 | 0.1 | 0.5 | 1.25 | 0.7 | 5.6 | yes |  |
| 3 | 0.75 | 0.1 | 0.5 | 1.5 | 0.7 | 5.6 | yes |  |
| 4 | 0.75 | 0.1 | 0.5 | 1.75 | 0.7 | 5.6 | yes |  |
| 5 | 0.75 | 0.15 | 0.5 | 1.25 | 0.7 | 5.6 | yes |  |
| 6 | 0.75 | 0.15 | 0.5 | 1.75 | 0.7 | 5.6 | yes |  |
| 7 | 1.0 | 0.1 | 0.5 | 1.25 | 0.7 | 5.3 | yes |  |
| 8 | 1.0 | 0.1 | 0.5 | 1.5 | 0.7 | 5.3 | yes |  |
| 9 | 0.5 | 0.1 | 0.5 | 1.25 | 0.7 | 5.2 | yes |  |
| 10 | 0.5 | 0.1 | 0.5 | 1.5 | 0.7 | 5.2 | yes |  |
| 11 | 0.5 | 0.1 | 0.5 | 1.75 | 0.7 | 5.2 | yes |  |
| 12 | 0.5 | 0.15 | 0.5 | 1.25 | 0.7 | 5.2 | yes |  |
| 13 | 0.5 | 0.15 | 0.5 | 1.5 | 0.7 | 5.2 | yes |  |
| 14 | 0.5 | 0.15 | 0.5 | 1.75 | 0.7 | 5.2 | yes |  |
| 15 | 0.5 | 0.25 | 0.5 | 1.25 | 0.7 | 5.2 | yes |  |

Default vector rank: **1 / 54** (agreement 0.7, separation 5.6).

Agreement is exact-band match against the expert windows. It is below 1.0
because the model is generous to thin/incidental evidence and the keyword
classifier under-counts paraphrased windows — the documented calibration
backlog (tests/eval/README.md). If a grid vector materially beats the default
on agreement without losing monotonicity, that is the signal to adopt it via a
governed scoring change.
