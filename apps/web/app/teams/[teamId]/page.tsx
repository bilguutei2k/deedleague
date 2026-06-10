import Link from "next/link";
import { notFound } from "next/navigation";
import {
  getTeam,
  getTeamStanding,
  getTeamGames,
  getTeamRoster,
  getTeamRollingDiff,
  getCurrentSeasonId,
  getSeasons,
} from "@deedleague/db";
import { SeasonSelector } from "@/components/SeasonSelector";
import { StatChart } from "@/components/StatChart";
import { displayName, fmtDate } from "@/lib/format";

export const dynamic = "force-dynamic";

export default async function TeamPage({
  params,
  searchParams,
}: {
  params: Promise<{ teamId: string }>;
  searchParams: Promise<{ season?: string }>;
}) {
  const { teamId } = await params;
  const sp = await searchParams;
  const [team, seasons, currentId] = await Promise.all([
    getTeam(teamId),
    getSeasons(),
    getCurrentSeasonId(),
  ]);
  if (!team) notFound();
  const seasonId = sp.season ?? currentId;
  const [standing, games, roster, diff] = await Promise.all([
    getTeamStanding(teamId, seasonId),
    getTeamGames(teamId, seasonId),
    getTeamRoster(teamId, seasonId),
    getTeamRollingDiff(teamId, seasonId),
  ]);

  return (
    <div className="space-y-8">
      <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
        <h1 className="text-xl font-semibold">{team.name}</h1>
        <SeasonSelector seasons={seasons} current={seasonId} basePath={`/teams/${teamId}`} />
      </div>

      {standing && (
        <p className="text-sm text-gray-700">
          Record <b>{standing.wins}–{standing.losses}</b> · PF {standing.pf} · PA {standing.pa} ·
          DIFF {standing.diff > 0 ? `+${standing.diff}` : standing.diff}
        </p>
      )}

      <section>
        <h2 className="mb-2 text-lg font-semibold">Point differential (cumulative)</h2>
        <StatChart data={diff} />
      </section>

      <div className="grid gap-8 md:grid-cols-2">
        <section>
          <h2 className="mb-2 text-lg font-semibold">Roster</h2>
          <table className="w-full border-collapse text-sm">
            <thead>
              <tr className="border-b border-gray-300 text-left text-gray-500">
                <th className="py-1 pr-2">#</th>
                <th className="pr-2">Player</th>
                <th className="px-2 text-right">GP</th>
              </tr>
            </thead>
            <tbody>
              {roster.map((p) => (
                <tr key={p.playerId} className="border-b border-gray-100">
                  <td className="py-1 pr-2 tabular-nums text-gray-500">{p.number ?? "—"}</td>
                  <td className="pr-2">
                    <Link href={`/players/${p.playerId}?season=${seasonId}`} className="hover:underline">
                      {displayName(p.name, p.surname)}
                    </Link>
                  </td>
                  <td className="px-2 text-right">{p.games}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>

        <section>
          <h2 className="mb-2 text-lg font-semibold">Games</h2>
          <ul className="divide-y divide-gray-100 text-sm">
            {games.map((g) => (
              <li key={g.gameId} className="py-1.5">
                <Link href={`/games/${g.gameId}`} className="flex items-center gap-2 hover:underline">
                  <span className="w-20 shrink-0 text-gray-500">{fmtDate(g.date)}</span>
                  <span className="w-6">{g.isWinner === null ? "" : g.isWinner ? "W" : "L"}</span>
                  <span className="tabular-nums">
                    {g.teamPts ?? "—"}–{g.oppPts ?? "—"}
                  </span>
                  <span className="flex-1 text-right text-gray-700">{g.oppName}</span>
                </Link>
              </li>
            ))}
          </ul>
        </section>
      </div>
    </div>
  );
}
