import assert from "node:assert/strict";
import test from "node:test";
import { readFileSync } from "node:fs";
import ts from "typescript";

async function sourceModule(name) {
  const source = readFileSync(new URL(`../src/${name}.ts`, import.meta.url), "utf8");
  const { outputText } = ts.transpileModule(source, { compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.ESNext } });
  return import(`data:text/javascript;base64,${Buffer.from(outputText).toString("base64")}`);
}

const { activeTime, activityTime, brokerToday, periodLabel, periodStart, responseTime, shiftPeriod, usageQuery } = await sourceModule("usage-analytics");
const { startHeartbeat } = await sourceModule("usage-heartbeat");

test("periods use broker dates, Monday weeks, DST-safe shifts and year boundaries", () => {
  assert.equal(brokerToday("America/Chicago", new Date("2026-01-01T02:00:00Z")), "2025-12-31");
  assert.equal(periodStart("week", "2026-01-04"), "2025-12-29");
  assert.equal(periodStart("week", "2026-01-05"), "2026-01-05");
  assert.equal(shiftPeriod("week", "2026-03-08", 1), "2026-03-09");
  assert.equal(shiftPeriod("day", "2026-03-08", -1), "2026-03-07");
  assert.equal(shiftPeriod("month", "2026-01-31", 1), "2026-02-01");
  assert.equal(shiftPeriod("month", "2025-12-20", 1), "2026-01-01");
  assert.equal(periodLabel("day", "2026-01-05", "2026-01-05"), "Today");
  assert.equal(periodLabel("week", "2026-01-05", "2026-01-11"), "This week");
  assert.match(periodLabel("week", "2025-12-29", "2026-01-12"), /Dec 29, 2025.*Jan 4, 2026/);
});

test("display formatting covers zero, null timestamps, timezone and response speed", () => {
  assert.equal(activeTime(0), "0:00");
  assert.equal(activeTime(125), "2:05");
  assert.equal(activityTime(null, "America/Chicago"), "—");
  assert.equal(activityTime("2026-01-01T02:00:00Z", "America/Chicago"), "Dec 31, 8:00 PM");
  assert.equal(responseTime(0), "0s");
  assert.equal(responseTime(720), "12m");
});

test("report query preserves identity exactly, admin exclusion and pagination", () => {
  const query = new URLSearchParams(usageQuery({ period: "week", date: "2026-01-05", exclude_admins: true }, { identity: "Tony & team", limit: 50, offset: 50 }));
  assert.equal(query.get("exclude_admins"), "true");
  assert.equal(query.get("identity"), "Tony & team");
  assert.equal(query.get("offset"), "50");
  const empty = new URLSearchParams(usageQuery({ period: "day", date: "2026-01-05", exclude_admins: false }));
  assert.equal(empty.get("exclude_admins"), "false");
  assert.equal(empty.has("identity"), false);
});

function heartbeatHarness(send) {
  const doc = new EventTarget();
  doc.visibilityState = "visible";
  const input = new EventTarget();
  let now = 0;
  let nextId = 0;
  const timers = new Map();
  const stop = startHeartbeat(send, {
    document: doc, input, now: () => now,
    setInterval: (callback, milliseconds) => { assert.equal(milliseconds, 30_000); timers.set(++nextId, callback); return nextId; },
    clearInterval: id => timers.delete(id),
  });
  return { doc, input, stop, timers, tick: (time) => { now = time; for (const callback of timers.values()) callback(); } };
}

test("heartbeat requires input, fires every active interval, expires at two minutes and cleans up", () => {
  let sends = 0;
  const harness = heartbeatHarness(async () => { sends++; });
  harness.tick(30_000);
  assert.equal(sends, 0);
  harness.input.dispatchEvent(new Event("pointerdown"));
  harness.tick(60_000);
  harness.tick(90_000);
  assert.equal(sends, 2);
  harness.tick(150_001);
  assert.equal(sends, 2);
  for (const event of ["pointermove", "keydown", "scroll", "touchstart"]) {
    harness.input.dispatchEvent(new Event(event));
    harness.tick(180_000);
  }
  assert.equal(sends, 6);
  harness.stop();
  assert.equal(harness.timers.size, 0);
  harness.input.dispatchEvent(new Event("keydown"));
  harness.tick(210_000);
  assert.equal(sends, 6);
});

test("hidden documents pause timers, ignore hidden input, and resume without stale input", () => {
  let sends = 0;
  const harness = heartbeatHarness(async () => { sends++; });
  harness.input.dispatchEvent(new Event("keydown"));
  harness.doc.visibilityState = "hidden";
  harness.doc.dispatchEvent(new Event("visibilitychange"));
  assert.equal(harness.timers.size, 0);
  harness.tick(180_000);
  harness.input.dispatchEvent(new Event("scroll"));
  harness.doc.visibilityState = "visible";
  harness.doc.dispatchEvent(new Event("visibilitychange"));
  harness.tick(210_000);
  assert.equal(sends, 0);
  harness.input.dispatchEvent(new Event("touchstart"));
  harness.tick(240_000);
  assert.equal(sends, 1);
  harness.stop();
});

test("heartbeat isolates network rejection and synchronous errors", async () => {
  const rejected = heartbeatHarness(() => Promise.reject(new Error("offline")));
  rejected.input.dispatchEvent(new Event("keydown"));
  assert.doesNotThrow(() => rejected.tick(30_000));
  await new Promise(resolve => setImmediate(resolve));
  rejected.stop();
  const thrown = heartbeatHarness(() => { throw new Error("offline"); });
  thrown.input.dispatchEvent(new Event("keydown"));
  assert.doesNotThrow(() => thrown.tick(30_000));
  thrown.stop();
});
