import { test } from "node:test";
import assert from "node:assert/strict";
import { rms, mouthScale } from "./audio.mjs";
test("silence closes mouth, amplitude drives bounded opening", () => {
  assert.equal(rms([]), 0);
  assert.equal(mouthScale([0, 0]), 0);
  assert.equal(rms([1, -1]), 1);
  assert.equal(mouthScale([1, -1]), 1);
  assert.ok(mouthScale([0.1, -0.1]) > mouthScale([0.01, -0.01]));
});
