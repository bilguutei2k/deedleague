import Link from "next/link";
import { notFound } from "next/navigation";
import { getGame, getBoxScore, getTerms, BOX_COLUMNS, pct1, num } from "@deedleague/db";
import { displayName, fmtDate } from "@/lib/format";

export const dynamic = "force-dynamic";

function cell(line: Record<string, number | null>, key: string, isPct?: boolean) {
  const v = line[key] ?? null;
  return isPct ? pct1(v) : num(v);
}

export default async function GamePage({ params }: { params: Promise<{ gameId: string }> }) {
  const { gameId } = await params;
  const [game, terms] = await Promise.all([getGame(gameId), getTerms()]);
  if (!game) notFound();
  const box = await getBoxScore(gameId, terms);

  return (
    <div className="space-y-6">
      <div>
        <p className="text-sm text-gray-500">
          {fmtDate(game.date)} · {game.seasonName.replace(/ ОНЫ УЛИРАЛ$/, "")} · {game.divisionName}
          {!game.isEnded && " · scheduled"}
        </p>
        <h1 className="flex items-center gap-3 text-xl font-semibold">
          {game.competitors.map((c, i) => (
            <span key={c.teamId} className="flex items-center gap-2">
              {i > 0 && <span className="text-gray-400">vs</span>}
              <Link href={`/teams/${c.teamId}`} className="hover:underline">
                {c.name}
              </Link>
              <span className="tabular-nums">{c.points ?? "—"}</span>
            </span>
          ))}
        </h1>
        <p className="text-xs text-gray-400">Shown in source order (home/away not asserted).</p>
      </div>

      {game.competitors.map((c) => {
        const players = box.byTeam.get(c.teamId) ?? [];
        const totals = box.totalsLine.get(c.teamId) ?? {};
        // One-sided source gap: the team has a real score but no recorded made-shots
        // (totals points = 0 while the official score is > 0), or no stats at all.
        const teamMadePts = Number(totals["BSKT_PTS"] ?? 0);
        const statless = (c.points ?? 0) > 0 && teamMadePts === 0;
        return (
          <section key={c.teamId} className="overflow-x-auto">
            <h2 className="mb-2 text-lg font-semibold">
              {c.name} <span className="font-normal text-gray-500">{c.points ?? "—"}</span>
              {statless && (
                <span className="ml-2 rounded border border-amber-300 bg-amber-50 px-1.5 py-0.5 text-xs text-amber-700">
                  partial: box score unavailable from source
                </span>
              )}
            </h2>
            <table className="border-collapse text-sm">
              <thead>
                <tr className="border-b border-gray-300 text-gray-500">
                  <th className="px-2 py-1 text-left">#</th>
                  <th className="px-2 py-1 text-left">Player</th>
                  {BOX_COLUMNS.map((col) => (
                    <th key={col.key} className="px-2 py-1 text-right">{col.label}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {players.map((p) => (
                  <tr key={p.playerId} className="border-b border-gray-100">
                    <td className="px-2 py-1 tabular-nums text-gray-500">{p.number ?? "—"}</td>
                    <td className="px-2 py-1">
                      <Link href={`/players/${p.playerId}`} className="hover:underline">
                        {displayName(p.name, p.surname)}
                      </Link>
                    </td>
                    {BOX_COLUMNS.map((col) => (
                      <td key={col.key} className="px-2 py-1 text-right tabular-nums">
                        {cell(p.line, col.key, col.pct)}
                      </td>
                    ))}
                  </tr>
                ))}
                {!statless && (
                  <tr className="border-t border-gray-300 font-medium">
                    <td />
                    <td className="px-2 py-1">Team</td>
                    {BOX_COLUMNS.map((col) => (
                      <td key={col.key} className="px-2 py-1 text-right tabular-nums">
                        {cell(totals, col.key, col.pct)}
                      </td>
                    ))}
                  </tr>
                )}
              </tbody>
            </table>
          </section>
        );
      })}
    </div>
  );
}
