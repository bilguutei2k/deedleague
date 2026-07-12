import Link from "next/link";
import { notFound } from "next/navigation";
import {
  getPlayer,
  getPlayerTeams,
  getPlayerSeasonLine,
  getPlayerGameLog,
  getTerms,
  getSeasonContext,
  BOX_COLUMNS,
  pct1,
  num,
} from "@deedleague/db";
import { SeasonSelector } from "@/components/SeasonSelector";
import { EmptySeasonState } from "@/components/EmptySeasonState";
import { displayName, fmtDate } from "@/lib/format";
import { withSeason } from "@/lib/season";

export const dynamic = "force-dynamic";

function cell(line: Record<string, number | null>, key: string, isPct?: boolean) {
  const v = line[key] ?? null;
  return isPct ? pct1(v) : num(v);
}

export default async function PlayerPage({
  params,
  searchParams,
}: {
  params: Promise<{ playerId: string }>;
  searchParams: Promise<{ season?: string }>;
}) {
  const { playerId } = await params;
  const sp = await searchParams;
  const [player, terms, context] = await Promise.all([
    getPlayer(playerId),
    getTerms(),
    getSeasonContext(sp.season),
  ]);
  if (!player) notFound();
  if (context.resolution.status === "invalid") notFound();
  if (context.resolution.status === "empty") return <EmptySeasonState />;
  const seasons = context.seasons;
  const seasonId = context.resolution.seasonId;
  const [teams, season, log] = await Promise.all([
    getPlayerTeams(playerId, seasonId),
    getPlayerSeasonLine(playerId, seasonId, terms),
    getPlayerGameLog(playerId, seasonId, terms),
  ]);

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h1 className="text-xl font-semibold">{displayName(player.name, player.surname)}</h1>
          <p className="text-sm text-gray-500">
            {teams.map((t, i) => (
              <span key={t.teamId}>
                {i > 0 && ", "}
                <Link href={withSeason(`/teams/${t.teamId}`, seasonId)} className="hover:underline">
                  {t.name}
                </Link>
              </span>
            ))}
          </p>
        </div>
        <SeasonSelector seasons={seasons} current={seasonId} basePath={`/players/${playerId}`} />
      </div>

      <p className="text-sm text-gray-700">Recorded appearances: {season.gamesPlayed}</p>

      <section className="overflow-x-auto">
        <h2 className="mb-2 text-lg font-semibold">Season totals</h2>
        <table className="border-collapse text-sm">
          <caption className="sr-only">Player season totals</caption>
          <thead>
            <tr className="border-b border-gray-300 text-gray-500">
              {BOX_COLUMNS.map((c) => (
                <th scope="col" key={c.key} className="px-2 py-1 text-right">{c.label}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            <tr>
              {BOX_COLUMNS.map((c) => (
                <td key={c.key} className="px-2 py-1 text-right tabular-nums">
                  {cell(season.line, c.key, c.pct)}
                </td>
              ))}
            </tr>
          </tbody>
        </table>
      </section>

      <section className="overflow-x-auto">
        <h2 className="mb-2 text-lg font-semibold">Game log</h2>
        <table className="border-collapse text-sm">
          <caption className="sr-only">Player game log</caption>
          <thead>
            <tr className="border-b border-gray-300 text-gray-500">
              <th scope="col" className="px-2 py-1 text-left">Date</th>
              {BOX_COLUMNS.map((c) => (
                <th scope="col" key={c.key} className="px-2 py-1 text-right">{c.label}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {log.map((row) => (
              <tr key={row.gameId} className="border-b border-gray-100">
                <td className="px-2 py-1">
                  <Link href={withSeason(`/games/${row.gameId}`, seasonId)} className="hover:underline">
                    {fmtDate(row.date)}
                  </Link>
                </td>
                {BOX_COLUMNS.map((c) => (
                  <td key={c.key} className="px-2 py-1 text-right tabular-nums">
                    {cell(row.line, c.key, c.pct)}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </section>
    </div>
  );
}
