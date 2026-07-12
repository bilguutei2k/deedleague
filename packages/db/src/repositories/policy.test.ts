import assert from "node:assert/strict";
import test from "node:test";

import {
  DEFAULT_LEADER_MIN_GAMES,
  getLeaderEligibility,
  LEADER_CATEGORIES,
  parseLeaderMinimumGames,
} from "./policy";

test("leader eligibility defaults to three recorded appearances", () => {
  assert.equal(parseLeaderMinimumGames(undefined), DEFAULT_LEADER_MIN_GAMES);
  assert.equal(getLeaderEligibility(undefined).minimumGames, 3);
  assert.equal(getLeaderEligibility(undefined).description, "Minimum 3 recorded appearances");
});

test("leader eligibility accepts a centralized configured threshold", () => {
  assert.equal(parseLeaderMinimumGames("3"), 3);
  assert.equal(getLeaderEligibility("3").description, "Minimum 3 recorded appearances");
});

test("leader eligibility rejects invalid thresholds", () => {
  for (const value of ["0", "-1", "1.5", "nope"]) {
    assert.throws(() => parseLeaderMinimumGames(value), /positive integer/);
  }
});

test("leader categories use atomic terms, including derived rebound inputs", () => {
  const rebounds = LEADER_CATEGORIES.find((category) => category.category === "reb");
  assert.deepEqual(rebounds?.terms, [
    { uniqueName: "BSKT_RO", weight: 1 },
    { uniqueName: "BSKT_RD", weight: 1 },
  ]);
});
