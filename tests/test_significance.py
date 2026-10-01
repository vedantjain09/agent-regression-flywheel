"""Tests for the McNemar's-test significance gate.

Each test builds a concrete paired-trial dataset and checks the resulting
decision, rather than asserting on p-value internals, since the whole point
of this module is the promotion decision it produces.
"""
import pytest

from app.stats.significance import PairedOutcome, mcnemar_exact, should_promote


def _pairs(baseline_pattern: list[bool], candidate_pattern: list[bool]) -> list[PairedOutcome]:
    assert len(baseline_pattern) == len(candidate_pattern)
    return [
        PairedOutcome(task_id=f"t{i}", seed=i, baseline_passed=b, candidate_passed=c)
        for i, (b, c) in enumerate(zip(baseline_pattern, candidate_pattern))
    ]


def test_identical_outcomes_are_never_significant():
    pattern = [True, False, True, True, False, True, False, True]
    outcomes = _pairs(pattern, pattern)
    result = mcnemar_exact(outcomes)
    assert result.significant is False
    assert result.direction == "no significant difference"
    promote, _ = should_promote(result)
    assert promote is False


def test_small_naive_pass_rate_gain_is_not_significant():
    # a classic trap: candidate "looks better" by a few points, but on a
    # handful of discordant pairs that's indistinguishable from a coin flip
    baseline = [True, True, False, True, False, True, True, False, True, False]
    candidate = [True, True, True, True, False, True, True, False, True, False]
    outcomes = _pairs(baseline, candidate)
    result = mcnemar_exact(outcomes)
    # only 1 discordant pair (index 2) — nowhere near enough evidence
    assert result.significant is False
    promote, reason = should_promote(result)
    assert promote is False
    assert "inconclusive" in reason


def test_clear_large_improvement_is_significant():
    # candidate passes everything baseline passed, plus wins on most of the
    # cases baseline failed — a real, large, consistent improvement
    n = 40
    baseline = [i % 3 == 0 for i in range(n)]  # baseline passes ~1/3
    candidate = [True if baseline[i] else (i % 4 != 0) for i in range(n)]  # candidate wins most of baseline's failures
    outcomes = _pairs(baseline, candidate)
    result = mcnemar_exact(outcomes)
    assert result.significant is True
    assert result.direction == "improved"
    promote, reason = should_promote(result)
    assert promote is True
    assert "promote" in reason


def test_clear_regression_is_significant_and_blocks_promotion():
    n = 40
    baseline = [i % 4 != 0 for i in range(n)]  # baseline passes ~3/4
    candidate = [False if baseline[i] else (i % 5 == 0) for i in range(n)]  # candidate loses most of baseline's passes
    outcomes = _pairs(baseline, candidate)
    result = mcnemar_exact(outcomes)
    assert result.significant is True
    assert result.direction == "regressed"
    promote, reason = should_promote(result)
    assert promote is False
    assert "block" in reason


def test_empty_outcomes_raises():
    with pytest.raises(ValueError):
        mcnemar_exact([])


def test_summary_includes_pair_counts():
    outcomes = _pairs([True, False], [False, True])
    result = mcnemar_exact(outcomes)
    summary = result.summary()
    assert "2 paired trials" in summary
    assert f"p={result.p_value:.4f}" in summary
