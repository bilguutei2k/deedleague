import Link from "next/link";
import { notFound } from "next/navigation";
import { getLeaders, getSeasonContext } from "@deedleague/db";
import { EmptySeasonState } from "@/components/EmptySeasonState";
import { SeasonSelector } from "@/components/SeasonSelector";
import { displayName } from "@/lib/format";
import { withSeason } from "@/lib/season";

export const dynamic = "force-dynamic";

export default async function LeadersPage({
  searchParams,
}: {
  searchParams: Promise<{ season?: string }>;
}) {
  const sp = await searchParams;
  const { seasons, resolution } = await getSeasonContext(sp.season);
  if (resolution.status === "invalid") notFound();
  if (resolution.status === "empty") return <EmptySeasonState />;
  const seasonId = resolution.seasonId;
  const leaders = await getLeaders(seasonId, 10);

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold">Leaders</h1>
        <SeasonSelector seasons={seasons} current={seasonId} basePath="/leaders" />
      </div>
      <p className="text-xs text-gray-500">
        Per-game averages over recorded stat appearances · {leaders.eligibility.description}.
      </p>

      <div className="grid gap-8 sm:grid-cols-2 lg:grid-cols-3">
        {leaders.categories.map((cat) => (
          <section key={cat.category}>
            <h2 className="mb-2 text-sm font-semibold text-gray-600">{cat.label}</h2>
            <ol className="space-y-1 text-sm">
              {cat.rows.map((r, i) => (
                <li key={r.playerId} className="flex items-center gap-2">
                  <span className="w-5 text-right text-gray-400">{i + 1}</span>
                  <Link href={withSeason(`/players/${r.playerId}`, seasonId)} className="flex-1 hover:underline">
                    {displayName(r.name, r.surname)}
                  </Link>
                  <span className="tabular-nums">{Number(r.value).toFixed(1)}</span>
                  <span className="w-8 text-right text-xs text-gray-400">{r.games}g</span>
                </li>
              ))}
            </ol>
          </section>
        ))}
      </div>
    </div>
  );
}
