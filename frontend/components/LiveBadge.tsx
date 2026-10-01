export default function LiveBadge({ live, label }: { live: boolean; label: string }) {
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-medium ${
        live
          ? "bg-emerald-950 text-emerald-400 ring-1 ring-emerald-800"
          : "bg-amber-950 text-amber-400 ring-1 ring-amber-800"
      }`}
      title={
        live
          ? `Live data from ${label}`
          : `${label} not configured/reachable — showing representative demo data in the same response shape`
      }
    >
      <span className={`h-1.5 w-1.5 rounded-full ${live ? "bg-emerald-400" : "bg-amber-400"}`} />
      {live ? "live" : "demo data"}
    </span>
  );
}
