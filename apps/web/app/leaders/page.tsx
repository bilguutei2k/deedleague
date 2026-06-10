import Link from "next/link";
import { getLeaders, getSeasons, getCurrentSeasonId } from "@deedleague/db";
import { SeasonSelector } from "@/components/SeasonSelector";
import { displayName } from "@/lib/format";

export const dynamic = "force-dynamic";

export default async function LeadersPage({
  searchParams,
}: {
  searchParams: Promise<{ season?: string }>;
}) {
  const sp = await searchParams;
  const [seasons, currentId] = await Promise.all([getSeasons(), getCurrentSeasonId()]);
  const seasonId = sp.season ?? currentId;
  const leaders = await getLeaders(seasonId, 10);

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold">Leaders</h1>
        <SeasonSelector seasons={seasons} current={seasonId} basePath="/leaders" />
      </div>
      <p className="text-xs text-gray-400">Per-game averages over statted games · no minimum threshold.</p>

      <div className="grid gap-8 sm:grid-cols-2 lg:grid-cols-3">
        {leaders.map((cat) => (
          <section key={cat.category}>
            <h2 className="mb-2 text-sm font-semibold text-gray-600">{cat.label}</h2>
            <ol className="space-y-1 text-sm">
              {cat.rows.map((r, i) => (
                <li key={r.playerId} className="flex items-center gap-2">
                  <span className="w-5 text-right text-gray-400">{i + 1}</span>
                  <Link href={`/players/${r.playerId}?season=${seasonId}`} className="flex-1 hover:underline">
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
