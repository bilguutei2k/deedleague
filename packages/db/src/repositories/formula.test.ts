import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

import { BOX_COLUMNS, computeLine, evaluateFormula, type Term } from "./formula";

const fixturePath = new URL(
  "../../../../pipeline/tests/fixtures/golden_game_44a47063.json",
  import.meta.url,
);
const fixture = JSON.parse(readFileSync(fixturePath, "utf8"));
const terms = fixture.data.game.division.tournament.terms.nodes as Term[];

test("every box-score column maps to an observed source term", () => {
  const names = new Set(terms.map((term) => term.uniqueName));
  for (const column of BOX_COLUMNS) {
    assert.ok(names.has(column.key), `missing source term for ${column.key}`);
  }
});

test("BKST_FGA is the observed derived FGA identifier", () => {
  const fga = terms.find((term) => term.uniqueName === "BKST_FGA");
  assert.ok(fga?.formula);
  assert.equal(
    evaluateFormula(fga.formula, { BSKT_1PTA: 0, BSKT_2PTA: 18, BSKT_3PTA: 8 }),
    26,
  );
  const line = computeLine(
    { BSKT_1PTA: 0, BSKT_2PTA: 18, BSKT_3PTA: 8 },
    terms,
  );
  assert.equal(line.BKST_FGA, 26);
});
