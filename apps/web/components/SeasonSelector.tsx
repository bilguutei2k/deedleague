import Link from "next/link";
import type { Season } from "@deedleague/db";

export function SeasonSelector({
  seasons,
  current,
  basePath,
}: {
  seasons: Season[];
  current: string;
  basePath: string;
}) {
  return (
    <nav className="flex flex-wrap items-center gap-2 text-sm">
      <span className="text-gray-500">Season:</span>
      {seasons.map((s) => {
        const active = s.id === current;
        const href = basePath + "?season=" + s.id;
        return (
          <Link
            key={s.id}
            href={href}
            className={
              "rounded border px-2 py-1 " +
              (active ? "border-gray-900 bg-gray-900 text-white" : "border-gray-300 text-gray-700")
            }
          >
            {s.name.replace(/ ОНЫ УЛИРАЛ$/, "")}
          </Link>
        );
      })}
    </nav>
  );
}
