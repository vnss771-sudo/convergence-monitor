"""Tunable scoring weights, externalized so they can be audited and calibrated.

The defaults reproduce the historical hand-set behavior exactly (so existing
golden/byte-stability tests are unchanged). `score_documents` accepts a
`ScoringWeights`; the calibration harness (`tools/calibrate_weights.py`) varies
these against a labeled evaluation set and proposes a justified vector.

These are still expert priors until the calibration report blesses a vector — see
docs/SCORING_GOVERNANCE.md and tests/eval/.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ScoringWeights:
    # Central-document component (basis, before SCORE_SCALE).
    central_per_doc: float = 0.75
    incidental_per_doc: float = 0.15
    central_cap: float = 3.0

    # Source-category diversity tiers (1, 2, 3+ active categories).
    diversity_one: float = 0.75
    diversity_two: float = 1.50
    diversity_many: float = 2.00

    # Trust-weight component.
    trust_multiplier: float = 0.5
    trust_cap: float = 2.0

    # Recency credit by document age (days) and the credit when age is unknown.
    recency_recent_days: int = 7
    recency_mid_days: int = 14
    recency_old_days: int = 30
    recency_recent_credit: float = 1.0
    recency_mid_credit: float = 0.7
    recency_old_credit: float = 0.4
    recency_stale_credit: float = 0.0
    recency_unknown_credit: float = 0.2

    # Duplicate-contributor penalty (basis).
    penalty_per_duplicate: float = 0.5
    penalty_cap: float = 2.0


DEFAULT_WEIGHTS = ScoringWeights()
