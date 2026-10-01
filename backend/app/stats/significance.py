"""Statistical significance for agent-version comparisons.

The naive approach — "baseline passed 72% of trials, candidate passed 76%,
ship it" — is frequently wrong, because LLM agent trials are stochastic: the
same task can pass on one rollout and fail on the next purely from sampling
variance. At the sample sizes most eval runs use (tens to low hundreds of
paired trials), a 4-point pass-rate difference is very often not
distinguishable from noise.

This module requires *paired* trials: the same task, same seed, run against
both the baseline and candidate agent version. McNemar's exact test is the
right tool for paired binary outcomes — it only looks at the discordant
pairs (where the two versions disagree) and asks whether the direction of
disagreement is asymmetric enough to not be chance, which is exactly the
question "did this change something" is actually asking.
"""
from __future__ import annotations

from dataclasses import dataclass

from scipy.stats import binomtest


@dataclass
class PairedOutcome:
    task_id: str
    seed: int
    baseline_passed: bool
    candidate_passed: bool


@dataclass
class SignificanceResult:
    n_pairs: int
    n_concordant: int  # both passed or both failed — uninformative for the test
    baseline_only_passed: int  # candidate regressed relative to baseline
    candidate_only_passed: int  # candidate improved relative to baseline
    p_value: float
    significant: bool
    direction: str  # "improved" | "regressed" | "no significant difference"

    def summary(self) -> str:
        return (
            f"{self.n_pairs} paired trials, {self.n_concordant} concordant "
            f"(ignored), {self.candidate_only_passed} candidate-only passes vs. "
            f"{self.baseline_only_passed} baseline-only passes, p={self.p_value:.4f} "
            f"-> {self.direction}"
        )


def mcnemar_exact(outcomes: list[PairedOutcome], alpha: float = 0.05) -> SignificanceResult:
    """Exact McNemar's test (binomial test on the discordant pairs), which
    is preferred over the chi-square approximation when the discordant-pair
    count is small — exactly the regime most agent regression suites run in,
    since hand-curated + mined task sets are rarely in the thousands."""
    if not outcomes:
        raise ValueError("need at least one paired outcome to run a significance test")

    baseline_only = sum(1 for o in outcomes if o.baseline_passed and not o.candidate_passed)
    candidate_only = sum(1 for o in outcomes if o.candidate_passed and not o.baseline_passed)
    concordant = len(outcomes) - baseline_only - candidate_only

    discordant_total = baseline_only + candidate_only
    if discordant_total == 0:
        # every pair agreed — no evidence of any difference, by construction
        return SignificanceResult(
            n_pairs=len(outcomes),
            n_concordant=concordant,
            baseline_only_passed=baseline_only,
            candidate_only_passed=candidate_only,
            p_value=1.0,
            significant=False,
            direction="no significant difference",
        )

    # Under H0 (no real difference), each discordant pair is a coin flip
    # for which version "won" it. Test whether candidate_only is far from
    # the expected 50% of the discordant pairs.
    result = binomtest(candidate_only, discordant_total, p=0.5, alternative="two-sided")
    p_value = float(result.pvalue)
    significant = bool(p_value < alpha)

    if not significant:
        direction = "no significant difference"
    elif candidate_only > baseline_only:
        direction = "improved"
    else:
        direction = "regressed"

    return SignificanceResult(
        n_pairs=len(outcomes),
        n_concordant=concordant,
        baseline_only_passed=baseline_only,
        candidate_only_passed=candidate_only,
        p_value=p_value,
        significant=significant,
        direction=direction,
    )


def should_promote(result: SignificanceResult) -> tuple[bool, str]:
    """The promotion gate: a candidate version is promotable only if the
    result is significant AND in the 'improved' direction. A significant
    regression blocks promotion outright; a non-significant result means
    "run more trials" rather than either a pass or a fail."""
    if result.direction == "improved":
        return True, f"promote: significant improvement ({result.summary()})"
    if result.direction == "regressed":
        return False, f"block: significant regression ({result.summary()})"
    return False, f"inconclusive: not statistically significant, need more trials ({result.summary()})"
