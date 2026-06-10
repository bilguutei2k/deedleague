// Formula engine — mirrors pipeline/statcalc.py. Evaluates the ONLY observed grammar:
// {TERM} refs, integer literals, + - * /, parentheses. Missing term -> 0. ÷0 -> null.
// Used to compute derived stats (PTS, FG%, …) from atomic counts at read time.

type Tok = { kind: "num" | "term" | "op" | "lpar" | "rpar"; value: string };

const TOKEN = /\s*(\{[A-Z0-9_]+\}|\d+\.?\d*|[()+\-*/])\s*/y;

function tokenize(formula: string): Tok[] {
  const toks: Tok[] = [];
  TOKEN.lastIndex = 0;
  let pos = 0;
  while (pos < formula.length) {
    TOKEN.lastIndex = pos;
    const m = TOKEN.exec(formula);
    if (!m || m.index !== pos) throw new Error(`bad token in formula: ${formula}`);
    pos = TOKEN.lastIndex;
    const t = m[1];
    if (t.startsWith("{")) toks.push({ kind: "term", value: t.slice(1, -1) });
    else if ("+-*/".includes(t)) toks.push({ kind: "op", value: t });
    else if (t === "(") toks.push({ kind: "lpar", value: t });
    else if (t === ")") toks.push({ kind: "rpar", value: t });
    else toks.push({ kind: "num", value: t });
  }
  return toks;
}

export function evaluateFormula(
  formula: string,
  counts: Record<string, number>,
): number | null {
  const toks = tokenize(formula);
  let i = 0;
  const peek = () => (i < toks.length ? toks[i] : null);

  function factor(): number | null {
    const t = peek();
    if (!t) throw new Error("unexpected end of formula");
    if (t.kind === "num") { i++; return Number(t.value); }
    if (t.kind === "term") { i++; return counts[t.value] ?? 0; }
    if (t.kind === "lpar") {
      i++;
      const v = expr();
      if (peek()?.kind !== "rpar") throw new Error("missing )");
      i++;
      return v;
    }
    throw new Error(`unexpected token ${t.value}`);
  }
  function term(): number | null {
    let v = factor();
    let t = peek();
    while (t && t.kind === "op" && (t.value === "*" || t.value === "/")) {
      i++;
      const rhs = factor();
      if (v === null || rhs === null) v = null;
      else if (t.value === "*") v = v * rhs;
      else v = rhs === 0 ? null : v / rhs;
      t = peek();
    }
    return v;
  }
  function expr(): number | null {
    let v = term();
    let t = peek();
    while (t && t.kind === "op" && (t.value === "+" || t.value === "-")) {
      i++;
      const rhs = term();
      if (v === null || rhs === null) v = null;
      else v = t.value === "+" ? v + rhs : v - rhs;
      t = peek();
    }
    return v;
  }
  const out = expr();
  if (i !== toks.length) throw new Error("trailing tokens in formula");
  return out;
}

export type Term = {
  id: string;
  uniqueName: string | null;
  shortName: string;
  formula: string | null;
  registrable: boolean | null;
  showOnUser: boolean | null;
  orderIndex: number | null;
};

// Compute a full stat line (atomic + derived) keyed by uniqueName from atomic counts.
export function computeLine(
  counts: Record<string, number>,
  terms: Term[],
): Record<string, number | null> {
  const line: Record<string, number | null> = {};
  for (const t of terms) {
    if (!t.uniqueName) continue;
    if (t.formula) line[t.uniqueName] = evaluateFormula(t.formula, counts);
    else line[t.uniqueName] = counts[t.uniqueName] ?? 0;
  }
  return line;
}

// Ordered box-score / line columns (uniqueName -> label). 3P%/2P% have no term, omitted.
export const BOX_COLUMNS: { key: string; label: string; pct?: boolean }[] = [
  { key: "BSKT_PTS", label: "PTS" },
  { key: "BSKT_FGM", label: "FGM" },
  { key: "BKST_FGA", label: "FGA" },
  { key: "BSKT_FG", label: "FG%", pct: true },
  { key: "BSKT_3PTM", label: "3PM" },
  { key: "BSKT_3PTA", label: "3PA" },
  { key: "BSKT_FTM", label: "FTM" },
  { key: "BSKT_FTA", label: "FTA" },
  { key: "BSKT_FT", label: "FT%", pct: true },
  { key: "BSKT_RO", label: "OR" },
  { key: "BSKT_RD", label: "DR" },
  { key: "BSKT_TOTRB", label: "REB" },
  { key: "BSKT_AS", label: "AST" },
  { key: "BSKT_ST", label: "STL" },
  { key: "BSKT_BS", label: "BLK" },
  { key: "BSKT_TO", label: "TO" },
  { key: "BSKT_PF", label: "PF" },
];

// Display helpers.
export function pct1(v: number | null): string {
  return v === null || v === undefined ? "—" : v.toFixed(1);
}
export function num(v: number | null): string {
  return v === null || v === undefined ? "—" : String(Math.round(v));
}
