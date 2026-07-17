import assert from "node:assert/strict";
import test from "node:test";

import { withSeason } from "./season";

test("season links preserve historical context", () => {
  assert.equal(withSeason("/games/game-1", "historical"), "/games/game-1?season=historical");
});

test("season links encode values and preserve existing query parameters", () => {
  assert.equal(withSeason("/leaders?view=all", "a/b"), "/leaders?view=all&season=a%2Fb");
});
