import type { Coverage } from "@deedleague/db";
import { fmtDate } from "@/lib/format";

export function CoverageBadge({ coverage }: { coverage: Coverage }) {
  const { full, partial, lastUpdated } = coverage;
  return (
    <div
      aria-label="Ingested game coverage"
      className="flex flex-wrap items-center gap-3 rounded border border-gray-300 px-3 py-2 text-sm"
    >
      <span className="font-medium">Ingested games</span>
      <span>full {full}</span>
      <span className="text-gray-500">·</span>
      <span>partial {partial}</span>
      <span className="text-gray-500">·</span>
      <span className="text-gray-500">loaded records only</span>
      {lastUpdated && (
        <span className="ml-auto text-gray-500">
          updated {fmtDate(lastUpdated)}
        </span>
      )}
    </div>
  );
}
