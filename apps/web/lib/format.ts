// Display helpers. Source stores name=family (e.g. "Moss"), surname=given ("Justin");
// "J. Moss" = given-initial + family. Names are shown as-returned otherwise.
export function displayName(name: string, surname?: string | null): string {
  const given = (surname ?? "").trim();
  return (given ? given[0] + ". " : "") + name;
}

export function fmtDate(iso: string): string {
  // Display in Asia/Ulaanbaatar (source instants are UTC).
  const d = new Date(iso);
  return new Intl.DateTimeFormat("en-CA", {
    timeZone: "Asia/Ulaanbaatar",
    year: "numeric", month: "2-digit", day: "2-digit",
  }).format(d);
}

export function pct3(v: number | null): string {
  if (v === null || v === undefined) return "—";
  return v.toFixed(3).replace(/^0/, "");
}
