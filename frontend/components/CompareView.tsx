"use client";

import { useState } from "react";
import { compareVersions } from "@/lib/api";
import type { CompareResponse, PairedOutcomeInput } from "@/lib/types";
import LiveBadge from "@/components/LiveBadge";

// Generates a synthetic paired-trial outcome set for the given scenario so
// the comparison view is explorable without a live regression run. The
// three scenarios map directly onto the three "trap" cases
// backend/tests/test_significance.py exercises against the real McNemar's
// implementation: a clear improvement, a clear regression, and a small
// naive pass-rate gain that is NOT statistically significant (the whole
// reason this project uses McNemar's test instead of a raw pass-rate diff).
type Scenario = "improvement" | "regression" | "noisy-gain";

function buildPairs(scenario: Scenario, n: number): PairedOutcomeInput[] {
  const pairs: PairedOutcomeInput[] = [];
  for (let i = 0; i < n; i++) {
    let baselinePassed: boolean;
    let candidatePassed: boolean;
    if (scenario === "improvement") {
      baselinePassed = i % 3 === 0;
      candidatePassed = baselinePassed || i % 4 !== 0;
    } else if (scenario === "regression") {
      candidatePassed = i % 3 === 0;
      baselinePassed = candidatePassed || i % 4 !== 0;
    } else {
      // noisy-gain: only 1 discordant pair out of n — a naive pass-rate
      // diff would look like an improvement, but it's noise.
      baselinePassed = i !== 0;
      candidatePassed = true;
    }
    pairs.push({ task_id: `task-${i % 8}`, seed: i, baseline_passed: baselinePassed, candidate_passed: candidatePassed });
  }
  return pairs;
}

const SCENARIOS: { id: Scenario; label: string; description: string }[] = [
  {
    id: "improvement",
    label: "Clear improvement",
    description: "Candidate fixes most of baseline's failures, few new regressions.",
  },
  {
    id: "regression",
    label: "Clear regression",
    description: "Candidate breaks tasks baseline used to pass.",
  },
  {
    id: "noisy-gain",
    label: "Small noisy gain",
    description: "Only 1 discordant pair — looks like a win on raw pass rate, isn't significant.",
  },
];

export default function CompareView({ initialResult, live }: { initialResult: CompareResponse; live: boolean }) {
  const [baseline, setBaseline] = useState("v1.4.0");
  const [candidate, setCandidate] = useState("v1.5.0-rc1");
  const [sampleSize, setSampleSize] = useState(40);
  const [scenario, setScenario] = useState<Scenario>("improvement");
  const [result, setResult] = useState<CompareResponse>(initialResult);
  const [isLive, setIsLive] = useState(live);
  const [loading, setLoading] = useState(false);

  async function runComparison() {
    setLoading(true);
    try {
      const pairs = buildPairs(scenario, sampleSize);
      const { result: newResult, live: newLive } = await compareVersions(baseline, candidate, pairs);
      setResult(newResult);
      setIsLive(newLive);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="grid grid-cols-1 gap-6 lg:grid-cols-[360px_1fr]">
      <div className="space-y-4 rounded-lg border border-neutral-800 bg-neutral-900/60 p-5">
        <div>
          <label className="block text-xs font-medium uppercase tracking-wide text-neutral-500">
            Baseline version
          </label>
          <input
            value={baseline}
            onChange={(e) => setBaseline(e.target.value)}
            className="mt-1 w-full rounded-md border border-neutral-700 bg-neutral-950 px-3 py-1.5 font-mono text-sm text-neutral-200"
          />
        </div>
        <div>
          <label className="block text-xs font-medium uppercase tracking-wide text-neutral-500">
            Candidate version
          </label>
          <input
            value={candidate}
            onChange={(e) => setCandidate(e.target.value)}
            className="mt-1 w-full rounded-md border border-neutral-700 bg-neutral-950 px-3 py-1.5 font-mono text-sm text-neutral-200"
          />
        </div>
        <div>
          <label className="block text-xs font-medium uppercase tracking-wide text-neutral-500">
            Trials per task (sample size)
          </label>
          <input
            type="number"
            min={2}
            max={200}
            value={sampleSize}
            onChange={(e) => setSampleSize(Number(e.target.value))}
            className="mt-1 w-full rounded-md border border-neutral-700 bg-neutral-950 px-3 py-1.5 font-mono text-sm text-neutral-200"
          />
        </div>
        <div>
          <label className="block text-xs font-medium uppercase tracking-wide text-neutral-500">
            Scenario
          </label>
          <div className="mt-2 space-y-2">
            {SCENARIOS.map((s) => (
              <label
                key={s.id}
                className={`block cursor-pointer rounded-md border p-3 text-sm transition-colors ${
                  scenario === s.id
                    ? "border-indigo-700 bg-indigo-950/50"
                    : "border-neutral-800 hover:border-neutral-700"
                }`}
              >
                <input
                  type="radio"
                  name="scenario"
                  value={s.id}
                  checked={scenario === s.id}
                  onChange={() => setScenario(s.id)}
                  className="sr-only"
                />
                <span className="font-medium text-neutral-200">{s.label}</span>
                <p className="mt-0.5 text-xs text-neutral-500">{s.description}</p>
              </label>
            ))}
          </div>
        </div>
        <button
          onClick={runComparison}
          disabled={loading}
          className="w-full rounded-md bg-indigo-700 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-600 disabled:opacity-50"
        >
          {loading ? "Running McNemar's test..." : "Run comparison"}
        </button>
      </div>

      <div className="space-y-4">
        <div className="flex items-center gap-2">
          <h2 className="text-sm font-semibold uppercase tracking-wide text-neutral-400">
            Significance result
          </h2>
          <LiveBadge live={isLive} label="FastAPI /runs/compare" />
        </div>

        <div
          className={`rounded-lg border p-6 ${
            result.promote
              ? "border-emerald-800 bg-emerald-950/30"
              : result.significant
                ? "border-red-800 bg-red-950/30"
                : "border-neutral-800 bg-neutral-900/60"
          }`}
        >
          <div className="flex items-baseline justify-between">
            <span className="text-3xl font-semibold text-neutral-100">
              {result.promote ? "PROMOTE" : result.significant ? "BLOCK" : "INCONCLUSIVE"}
            </span>
            <span className="font-mono text-sm text-neutral-400">
              p = {result.p_value.toFixed(6)}
            </span>
          </div>
          <p className="mt-2 text-sm text-neutral-300">{result.reason}</p>
          <p className="mt-1 text-xs text-neutral-500">direction: {result.direction}</p>
        </div>

        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
          <Stat label="Total pairs" value={result.n_pairs} />
          <Stat label="Concordant" value={result.n_concordant} />
          <Stat label="Baseline-only pass" value={result.baseline_only_passed} />
          <Stat label="Candidate-only pass" value={result.candidate_only_passed} />
        </div>

        <p className="text-xs leading-relaxed text-neutral-500">
          McNemar&rsquo;s exact test only looks at the discordant pairs — trials where baseline and
          candidate disagree — and asks whether the direction of disagreement is more lopsided
          than coin-flip noise would produce. A raw pass-rate diff can&rsquo;t tell &ldquo;candidate
          genuinely fixed real failures&rdquo; apart from &ldquo;one flaky trial happened to flip,&rdquo;
          which is exactly what the small-noisy-gain scenario demonstrates.
        </p>
      </div>
    </div>
  );
}

function Stat({ label, value }: { label: string; value: number }) {
  return (
    <div className="rounded-lg border border-neutral-800 bg-neutral-900/60 p-3">
      <p className="text-xs text-neutral-500">{label}</p>
      <p className="mt-1 text-lg font-semibold text-neutral-100">{value}</p>
    </div>
  );
}
