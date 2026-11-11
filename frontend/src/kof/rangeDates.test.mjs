import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";
import ts from "typescript";

const source = ts.transpileModule(readFileSync(new URL("./rangeDates.ts", import.meta.url), "utf8"), { compilerOptions: { module: ts.ModuleKind.ESNext } }).outputText;
const { brokerDay, shiftDay, weekStart, clampDay } = await import(`data:text/javascript;base64,${Buffer.from(source).toString("base64")}`);

test("today uses broker timezone across UTC midnight and DST", () => {
  assert.equal(brokerDay("America/Chicago", new Date("2026-11-09T02:00:00Z")), "2026-11-08");
  assert.equal(brokerDay("Asia/Tokyo", new Date("2026-11-09T02:00:00Z")), "2026-11-09");
  assert.equal(brokerDay("America/Chicago", new Date("2026-03-08T07:30:00Z")), "2026-03-08");
});

test("weeks run Monday through Sunday, including year and DST boundaries", () => {
  for (const [day, monday, sunday] of [
    ["2026-11-02", "2026-11-02", "2026-11-08"],
    ["2026-11-08", "2026-11-02", "2026-11-08"],
    ["2027-01-01", "2026-12-28", "2027-01-03"],
    ["2026-03-08", "2026-03-02", "2026-03-08"],
  ]) {
    assert.equal(weekStart(day), monday);
    assert.equal(shiftDay(weekStart(day), 6), sunday);
  }
  assert.equal(shiftDay("2026-11-02", -7), "2026-10-26");
});

test("invalid, empty and future selections resolve to today", () => {
  for (const day of [null, "", "bad", "2026-02-30", "2026-11-10"]) {
    assert.equal(clampDay(day, "2026-11-09"), "2026-11-09");
  }
  assert.equal(clampDay("2026-11-08", "2026-11-09"), "2026-11-08");
});
