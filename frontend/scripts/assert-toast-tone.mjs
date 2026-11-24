/** Lightweight guard for toast tone aliases (no vitest harness in frontend/). */
import assert from "node:assert/strict";

function normalizeToastTone(tone) {
  if (tone === "error") return "attention";
  if (tone === "info") return "system";
  return tone;
}

assert.equal(normalizeToastTone("error"), "attention");
assert.equal(normalizeToastTone("info"), "system");
assert.equal(normalizeToastTone("success"), "success");
assert.equal(normalizeToastTone("signal"), "signal");
assert.equal(normalizeToastTone("attention"), "attention");
assert.equal(normalizeToastTone("system"), "system");

console.log("toast tone aliases ok");
