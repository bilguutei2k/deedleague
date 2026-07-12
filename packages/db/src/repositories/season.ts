export type SeasonResolution =
  | { status: "resolved"; seasonId: string }
  | { status: "empty"; seasonId: null }
  | { status: "invalid"; seasonId: null };

export function resolveSeasonId(
  seasons: { id: string }[],
  requested: string | undefined,
  configuredCurrent: string | undefined,
): SeasonResolution {
  if (requested) {
    return seasons.some((season) => season.id === requested)
      ? { status: "resolved", seasonId: requested }
      : { status: "invalid", seasonId: null };
  }
  if (configuredCurrent && seasons.some((season) => season.id === configuredCurrent)) {
    return { status: "resolved", seasonId: configuredCurrent };
  }
  const latest = seasons[0]?.id;
  return latest
    ? { status: "resolved", seasonId: latest }
    : { status: "empty", seasonId: null };
}
