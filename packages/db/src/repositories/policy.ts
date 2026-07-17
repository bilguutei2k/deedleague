export const DEFAULT_LEADER_MIN_GAMES = 3;

export type LeaderEligibility = {
  minimumGames: number;
  description: string;
};

export type LeaderCategorySpec = {
  category: string;
  label: string;
  terms: { uniqueName: string; weight: number }[];
};

export const LEADER_CATEGORIES: LeaderCategorySpec[] = [
  {
    category: "pts",
    label: "Points / game",
    terms: [
      { uniqueName: "BSKT_2PTM", weight: 2 },
      { uniqueName: "BSKT_3PTM", weight: 3 },
      { uniqueName: "BSKT_FTM", weight: 1 },
      { uniqueName: "BSKT_1PTM", weight: 1 },
    ],
  },
  {
    category: "reb",
    label: "Rebounds / game",
    terms: [
      { uniqueName: "BSKT_RO", weight: 1 },
      { uniqueName: "BSKT_RD", weight: 1 },
    ],
  },
  { category: "ast", label: "Assists / game", terms: [{ uniqueName: "BSKT_AS", weight: 1 }] },
  { category: "stl", label: "Steals / game", terms: [{ uniqueName: "BSKT_ST", weight: 1 }] },
  { category: "blk", label: "Blocks / game", terms: [{ uniqueName: "BSKT_BS", weight: 1 }] },
];

export function parseLeaderMinimumGames(raw: string | undefined): number {
  if (raw === undefined || raw.trim() === "") return DEFAULT_LEADER_MIN_GAMES;
  const value = Number(raw);
  if (!Number.isSafeInteger(value) || value < 1) {
    throw new Error("LEADER_MIN_GAMES must be a positive integer");
  }
  return value;
}

export function getLeaderEligibility(raw = process.env.LEADER_MIN_GAMES): LeaderEligibility {
  const minimumGames = parseLeaderMinimumGames(raw);
  return {
    minimumGames,
    description: `Minimum ${minimumGames} recorded appearance${minimumGames === 1 ? "" : "s"}`,
  };
}
