import Link from "next/link";
import {
  getSeasons,
  getCurrentSeasonId,
  getStandings,
  getCoverage,
  getRecentResults,
  getLeaders,
} from "@deedleague/db";
import { SeasonSelector } from "@/components/SeasonSelector";
import { CoverageBadge } from "@/components/CoverageBadge";
import { displayName, fmtDate, pct3 } from "@/lib/format";

export const dynamic = "force-dynamic";

export default async function HomePage({
  searchParams,
}: {
  searchParams: Promise<{ season?: string }>;
}) {
  const sp = await searchParams;
  const [seasons, currentId] = await Promise.all([getSeasons(), getCurrentSeasonId()]);
  const seasonId = sp.season ?? currentId;
  const [standings, coverage, results, leaders] = await Promise.all([
    getStandings(seasonId),
    getCoverage(seasonId),
    getRecentResults(seasonId, 8),
    getLeaders(seasonId, 5),
  ]);

  return (
    <div className="space-y-8">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <SeasonSelector seasons={seasons} current={seasonId} basePath="/" />
        <CoverageBadge coverage={coverage} />
      </div>

      <section>
        <h2 className="mb-2 text-lg font-semibold">Standings</h2>
        <table className="w-full border-collapse text-sm">
          <thead>
            <tr className="border-b border-gray-300 text-left text-gray-500">
              <th className="py-1 pr-2">Team</th>
              <th className="px-2 text-right">W</th>
              <th className="px-2 text-right">L</th>
              <th className="px-2 text-right">PCT</th>
              <th className="px-2 text-right">PF</th>
              <th className="px-2 text-right">PA</th>
              <th className="px-2 text-right">DIFF</th>
            </tr>
          </thead>
          <tbody>
            {standings.map((r) => (
              <tr key={r.teamId} className="border-b border-gray-100">
                <td className="py-1 pr-2">
                  <Link href={`/teams/${r.teamId}?season=${seasonId}`} className="hover:underline">
                    {r.name}
                  </Link>
                </td>
                <td className="px-2 text-right">{r.wins}</td>
                <td className="px-2 text-right">{r.losses}</td>
                <td className="px-2 text-right">{pct3(r.pct === null ? null : Number(r.pct))}</td>
                <td className="px-2 text-right">{r.pf}</td>
                <td className="px-2 text-right">{r.pa}</td>
                <td className="px-2 text-right">{r.diff > 0 ? `+${r.diff}` : r.diff}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>

      <div className="grid gap-8 md:grid-cols-2">
        <section>
          <h2 className="mb-2 text-lg font-semibold">Recent results</h2>
          <ul className="divide-y divide-gray-100 text-sm">
            {results.map((g) => (
              <li key={g.gameId} className="py-1.5">
                <Link href={`/games/${g.gameId}`} className="flex items-center gap-2 hover:underline">
                  <span className="w-20 shrink-0 text-gray-500">{fmtDate(g.date)}</span>
                  <span className="flex-1">{g.aName}</span>
                  <span className="tabular-nums">
                    {g.aPts}–{g.bPts}
                  </span>
                  <span className="flex-1 text-right">{g.bName}</span>
                </Link>
              </li>
            ))}
          </ul>
        </section>

        <section>
          <h2 className="mb-2 text-lg font-semibold">Leaders</h2>
          <div className="space-y-3 text-sm">
            {leaders.map((cat) => (
              <div key={cat.category}>
                <div className="text-gray-500">{cat.label}</div>
                <ol className="ml-4 list-decimal">
                  {cat.rows.slice(0, 3).map((r) => (
                    <li key={r.playerId}>
                      <Link href={`/players/${r.playerId}?season=${seasonId}`} className="hover:underline">
                        {displayName(r.name, r.surname)}
                      </Link>{" "}
                      <span className="tabular-nums text-gray-700">{Number(r.value).toFixed(1)}</span>
                    </li>
                  ))}
                </ol>
              </div>
            ))}
          </div>
        </section>
      </div>
    </div>
  );
}
