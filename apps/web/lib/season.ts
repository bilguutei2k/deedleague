export function withSeason(path: string, seasonId: string): string {
  const separator = path.includes("?") ? "&" : "?";
  return `${path}${separator}season=${encodeURIComponent(seasonId)}`;
}
