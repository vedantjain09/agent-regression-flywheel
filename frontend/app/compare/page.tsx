import { compareVersions } from "@/lib/api";
import CompareView from "@/components/CompareView";

export default async function ComparePage() {
  // Seed the view with a representative "clear improvement" comparison so
  // the page is non-empty on first load; CompareView lets the user re-run
  // it against any scenario/sample size from there.
  const seedPairs = Array.from({ length: 40 }, (_, i) => {
    const baseline_passed = i % 3 === 0;
    return {
      task_id: `task-${i % 8}`,
      seed: i,
      baseline_passed,
      candidate_passed: baseline_passed || i % 4 !== 0,
    };
  });
  const { result, live } = await compareVersions("v1.4.0", "v1.5.0-rc1", seedPairs);

  return (
    <main className="mx-auto max-w-6xl px-6 py-10">
      <div className="mb-8">
        <h1 className="text-xl font-semibold text-neutral-100">Version Comparison</h1>
        <p className="mt-1 text-sm text-neutral-400">
          Replays the approved regression suite against a baseline and candidate agent version,
          then gates promotion behind McNemar&rsquo;s exact test on the paired outcomes — not a
          naive pass-rate diff.
        </p>
      </div>
      <CompareView initialResult={result} live={live} />
    </main>
  );
}
