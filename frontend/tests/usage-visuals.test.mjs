import assert from "node:assert/strict";
import test from "node:test";
import { readFileSync } from "node:fs";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import ts from "typescript";

const url = code => `data:text/javascript;base64,${Buffer.from(code).toString("base64")}`;
const compile = path => ts.transpileModule(readFileSync(new URL(path, import.meta.url), "utf8"), { compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.ESNext, jsx: ts.JsxEmit.ReactJSX } }).outputText;
const helpers = url(compile("../src/usage-visuals.ts"));
const { categoryMix, contributionCells, freshness, localHour, personColor, timeAgo } = await import(helpers);
const ui = url(`import {createElement} from "${import.meta.resolve("react")}"; export const Card = p => createElement("section", p); export const Button = p => createElement("button", p);`);
const source = compile("../src/components/UsageCharts.tsx").replaceAll('"./ui"', JSON.stringify(ui)).replaceAll('"../usage-visuals"', JSON.stringify(helpers)).replaceAll('"react/jsx-runtime"', JSON.stringify(import.meta.resolve("react/jsx-runtime")));
const { ActionBars, ChartCard, Contributions, Radar, SeriesChart, Sparkline } = await import(url(source));
const render = (Component, props) => renderToStaticMarkup(createElement(Component, props));
const person = { identity: "Tony", devices: { mobile: 3 }, series: [{ date: "2026-11-08", active_minutes: 3, actions: 4, categories: { bol: 1, chat: 3 } }] };

test("identity colors, category normalization, broker clock and freshness boundaries", () => {
  assert.equal(personColor("Tony"), personColor("TONY"));
  assert.notEqual(personColor("Tony"), personColor("Kolby"));
  assert.deepEqual(categoryMix(), Array(8).fill(0));
  assert.equal(categoryMix(person)[0], .25);
  assert.equal(categoryMix(person)[3], .75);
  assert.equal(localHour("2026-11-09T02:30:00Z", "America/Chicago"), 20.5);
  assert.equal(timeAgo(null), "Never");
  assert.equal(timeAgo("2026-11-08T00:00:00Z", Date.parse("2026-11-08T00:01:30Z")), "1m ago");
  assert.equal(freshness(3600).label, "Fresh");
  assert.equal(freshness(3601).label, "Delayed");
  assert.equal(freshness(86401).label, "Stale");
  assert.equal(freshness(null).label, "No successful sync");
});

test("contributions preserve every date, Monday alignment, intensity and accessible drilldown", () => {
  assert.deepEqual(contributionCells([]), []);
  const days = Array.from({ length: 365 }, (_, i) => ({ date: new Date(Date.UTC(2025, 10, 9 + i)).toISOString().slice(0, 10), count: i % 5, active_minutes: i % 3, actions: 1 }));
  const cells = contributionCells(days);
  assert.equal(cells.length, 371);
  assert.equal(cells.filter(Boolean).length, 365);
  const html = render(Contributions, { days, identity: "Tony", onDay: () => {} });
  assert.equal((html.match(/<button/g) ?? []).length, 365);
  assert.match(html, /Open Tony activity for 2025-11-09/);
  assert.match(html, /Nov/);
  assert.match(render(Contributions, { days: [], identity: "Tony", onDay: () => {} }), /No contribution history/);
});

test("all SVG charts support normal, empty and sparse data without invalid geometry", () => {
  for (const stacked of [false, true]) {
    const html = render(SeriesChart, { labels: ["Mon", "Tue", "Wed"], series: [{ name: "Tony", values: [5, null, -2] }], unit: "profit", stacked });
    assert.match(html, /Tony/);
    assert.doesNotMatch(html, /NaN|Infinity/);
  }
  assert.match(render(SeriesChart, { labels: [], series: [], unit: "minutes" }), /No activity to chart/);
  assert.match(render(Radar, { team: [] }), /No category actions/);
  assert.match(render(Radar, { person, team: [person] }), /Category percentages/);
  assert.match(render(ActionBars, { people: [person] }), /4 actions/);
  assert.match(render(ActionBars, { people: [] }), /No activity/);
  assert.doesNotMatch(render(Sparkline, { values: [0, 0, 0], identity: "Tony" }), /NaN|Infinity/);
});

test("chart boundaries provide loading, empty children and recoverable errors", () => {
  assert.match(render(ChartCard, { title: "Timeline", pending: true, children: "Hidden" }), /Loading timeline/);
  assert.doesNotMatch(render(ChartCard, { title: "Timeline", pending: true, children: "Hidden" }), /Hidden/);
  assert.match(render(ChartCard, { title: "Timeline", error: Error("Offline"), children: "Hidden" }), /Offline.*Retry/);
  assert.match(render(ChartCard, { title: "Timeline", children: "No data" }), /No data/);
});
