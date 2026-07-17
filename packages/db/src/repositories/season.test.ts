import assert from "node:assert/strict";
import test from "node:test";

import { resolveSeasonId } from "./season";

const seasons = [{ id: "current" }, { id: "historical" }];

test("season resolution reports an empty database", () => {
  assert.deepEqual(resolveSeasonId([], undefined, undefined), {
    status: "empty",
    seasonId: null,
  });
});

test("season resolution rejects an invalid requested season", () => {
  assert.deepEqual(resolveSeasonId(seasons, "unknown", undefined), {
    status: "invalid",
    seasonId: null,
  });
});

test("season resolution uses the configured current season when valid", () => {
  assert.deepEqual(resolveSeasonId(seasons, undefined, "historical"), {
    status: "resolved",
    seasonId: "historical",
  });
});

test("season resolution preserves an explicitly requested historical season", () => {
  assert.deepEqual(resolveSeasonId(seasons, "historical", "current"), {
    status: "resolved",
    seasonId: "historical",
  });
});
