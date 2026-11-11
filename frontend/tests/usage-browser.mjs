import fs from "node:fs";
import assert from "node:assert/strict";

const cdp = process.env.CDP_URL ?? "http://localhost:29229";
const origin = process.env.APP_URL ?? "http://localhost:5173";
const screenshots = process.env.SCREENSHOTS ?? "/home/ubuntu/screenshots";
const target = await (await fetch(`${cdp}/json/new?about:blank`, { method: "PUT" })).json();
const ws = new WebSocket(target.webSocketDebuggerUrl);
await new Promise(resolve => ws.addEventListener("open", resolve));
let id = 0;
const pending = new Map();
ws.onmessage = event => {
  const message = JSON.parse(event.data);
  if (message.id) { pending.get(message.id)?.(message); pending.delete(message.id); }
};
const call = (method, params = {}) => new Promise(resolve => {
  const next = ++id; pending.set(next, resolve); ws.send(JSON.stringify({ id: next, method, params }));
});
const run = async expression => {
  const result = await call("Runtime.evaluate", { expression, awaitPromise: true, returnByValue: true });
  if (result.error?.message?.includes("navigated")) return undefined;
  if (result.error || result.result?.exceptionDetails) throw Error(JSON.stringify(result));
  return result.result?.result?.value;
};
async function ready(expression) {
  for (let attempt = 0; attempt < 1200; attempt++) {
    if (await run(`new Promise(resolve => requestAnimationFrame(() => resolve(${expression})))`)) { await run("document.fonts.ready"); return; }
  }
  throw Error(`Not ready: ${expression}\n${await run("document.body.innerText")}`);
}
const clickTab = name => run(`Array.from(document.querySelectorAll('[aria-label="Usage reports"] [role="tab"]')).find(el => el.textContent === ${JSON.stringify(name)}).click()`);
async function shot(name, full = false) {
  assert.equal(await run("document.documentElement.scrollWidth > 390"), false, "No horizontal page overflow");
  const metrics = await call("Page.getLayoutMetrics");
  const screenshot = await call("Page.captureScreenshot", { format: "png", captureBeyondViewport: full, ...(full ? { clip: { x: 0, y: 0, width: 390, height: metrics.result.cssContentSize.height, scale: 1 } } : {}) });
  fs.writeFileSync(`${screenshots}/${name}.png`, Buffer.from(screenshot.result.data, "base64"));
}

function fixture() {
  const RealDate = Date;
  window.Date = class extends RealDate {
    constructor(...args) { super(...(args.length ? args : ["2026-11-09T02:00:00Z"])); }
    static now() { return new RealDate("2026-11-09T02:00:00Z").getTime(); }
  };
  const original = window.fetch.bind(window);
  window.fixtureRequests = [];
  window.fixtureMode = "normal";
  const intervals = new Map();
  const originalInterval = window.setInterval.bind(window);
  const originalClear = window.clearInterval.bind(window);
  let nextTimer = 100000;
  window.setInterval = (callback, ms, ...args) => {
    if (ms !== 30000) return originalInterval(callback, ms, ...args);
    const id = ++nextTimer; intervals.set(id, callback); return id;
  };
  window.clearInterval = id => { if (!intervals.delete(id)) originalClear(id); };
  window.tickHeartbeat = () => { for (const callback of intervals.values()) callback(); };
  window.fetch = async (url, options = {}) => {
    const path = String(url);
    if (!path.startsWith("/api/")) return original(url, options);
    window.fixtureRequests.push({ path, body: options.body });
    const parsed = new URL(path, location.origin);
    const query = parsed.searchParams;
    const role = sessionStorage.getItem("analytics-fixture-role") ?? "admin";
    let data = [];
    let status = 200;
    if (parsed.pathname === "/api/auth/me") data = { authenticated: true, role, username: "Jadin", broker_timezone: "America/Chicago", operator: role === "member" ? { id: 1, name: "Scotti" } : null, team_members_exist: true, must_set_password: false, can_claim_admin: false };
    else if (parsed.pathname === "/api/integrations/status") data = { sms_live: false, email_live: false, assistant_live: false };
    else if (parsed.pathname === "/api/kof/sync") data = { configured: false, running: false, load_count: 0 };
    else if (parsed.pathname.startsWith("/api/usage/")) data = { accepted: true };
    else if (parsed.pathname.startsWith("/api/admin/usage/")) {
      const meta = { period: query.get("period"), date: query.get("date"), exclude_admins: query.get("exclude_admins") === "true", timezone: "America/Chicago", start: "2026-11-02T00:00:00-06:00", end_exclusive: "2026-11-09T00:00:00-06:00" };
      const empty = window.fixtureMode === "empty";
      const names = empty ? [] : ["Scotti", "Tony", "Kolby", ...(meta.exclude_admins ? [] : ["Jadin"])];
      const people = names.map((identity, index) => ({ identity, active_minutes: 365 - index * 60, sessions: 8 - index, first_activity: "2026-11-02T08:05:00-06:00", last_activity: "2026-11-08T17:20:00-06:00", avg_session_minutes: 45, days_active: 5, current_streak: 3, actions: 42 - index * 8, action_counts: { customer_update_approve: 14, assistant_question: 12, kof_text_send: 10, kof_email_draft: 6 }, chat_questions: 12 }));
      const section = parsed.pathname.split("/").at(-1);
      if (window.fixtureMode === "error") { status = 503; data = { detail: "Analytics temporarily unavailable" }; }
      else if (section === "people") data = { ...meta, people };
      else if (section === "pages") data = { ...meta, pages: names.flatMap(identity => [{ identity, path: "/tracking", active_minutes: 145 }, { identity, path: "/loads", active_minutes: 105 }, { identity, path: "/customer-updates", active_minutes: 45 }]) };
      else if (section === "leaderboard") data = { ...meta, people: people.map((person, index) => ({ ...person, kof_profit: index === 2 ? null : 5200 - index * 1000, active_minutes_rank: index + 1, actions_rank: index + 1, kof_profit_rank: index === 2 ? null : index + 1 })) };
      else if (section === "heatmap") {
        const cells = names.flatMap((identity, index) => Array.from({ length: 50 }, (_, cell) => ({ identity, weekday: Math.floor(cell / 10), hour: cell % 10 + 8, active_minutes: (cell + index * 3) % 12 + 1 })));
        const totals = new Map();
        for (const cell of cells) {
          const key = `${cell.weekday}:${cell.hour}`;
          totals.set(key, { weekday: cell.weekday, hour: cell.hour, active_minutes: cell.active_minutes + (totals.get(key)?.active_minutes ?? 0) });
        }
        data = { ...meta, cells, total: [...totals.values()] };
      } else if (section === "feed") {
        let items = empty ? [] : Array.from({ length: 52 }, (_, index) => ({ id: 1000 - index, identity: names[index % names.length], event: index === 1 ? "assistant_question" : "customer_update_approve", path: index === 1 ? "/tracking" : "/customer-updates", device: "mobile", time: "2026-11-08T14:12:00-06:00", summary: index === 1 ? "Asked assistant" : `Approved customer update for order ${3425326 + index}`, detail: index === 1 ? { question: "Did BOL #90123 get loaded? Show the latest carrier update." } : { order_no: String(3425326 + index) } }));
        if (query.get("identity")) items = items.filter(item => item.identity === query.get("identity"));
        const offset = Number(query.get("offset"));
        data = { ...meta, items: items.slice(offset, offset + 50), total: items.length, limit: 50, offset, has_more: offset + 50 < items.length };
      } else if (section === "kof_output") {
        const rows = empty ? [] : [{ name: "Scotti", loads: 18, revenue: 42000, carrier_cost: 35000, profit: 7000, margin_pct: 16.7 }];
        data = { ...meta, booker: rows, rep: rows };
      } else if (section === "response_speed") data = { ...meta, people: empty ? [] : [{ identity: "Tony", count: 14, median_seconds: 720, avg_seconds: 900 }], unlinked_approval_events: 1 };

      else if (section === "contributions") data = { ...meta, people: names.map(identity => ({ identity, current_streak: 4, longest_streak: 12, days: Array.from({ length: 365 }, (_, i) => { const stamp = new RealDate(query.get("date") + "T12:00:00Z"); stamp.setUTCDate(stamp.getUTCDate() - 364 + i); return { date: stamp.toISOString().slice(0, 10), count: i % 7 < 5 ? i % 12 + 1 : 0, active_minutes: i % 9, actions: i % 4 }; }) })) };
      else if (section === "live") data = { ...meta, as_of: new Date().toISOString(), people: names.map(identity => ({ identity, path: "/tracking", device: "mobile", last_heartbeat: "2026-11-09T01:59:30Z", last_action: { time: "2026-11-09T01:58:00Z", event: "customer_update_approve", summary: "Approved customer update for order 3425326" } })) };
      else if (section === "users_overview") data = { ...meta, week_start: "2026-11-02", users: empty ? [] : [...names, "Pat (never active)"].map((identity, i) => ({ kind: i === 0 ? "user" : "team_member", id: i + 1, identity, role: i === 0 ? "member" : null, is_active: i !== 3, last_seen: i === 3 ? null : "2026-11-09T01:59:30Z", active_minutes_this_week: i === 3 ? 0 : 340, actions_this_week: i === 3 ? 0 : 42, sparkline: Array.from({ length: 7 }, (_, d) => ({ date: "2026-11-0" + (d + 2), active_minutes: i === 3 ? 0 : [20, 36, 80, 75, 50, 20, 59][d], actions: d })) })) };
      else if (section === "timeline") data = { ...meta, people: names.map(identity => ({ identity, spans: [{ start: query.get("date") + "T08:15:00-06:00", end_exclusive: query.get("date") + "T11:40:00-06:00", active_minutes: 180 }, { start: query.get("date") + "T13:00:00-06:00", end_exclusive: query.get("date") + "T17:20:00-06:00", active_minutes: 200 }], actions: [{ time: query.get("date") + "T14:00:00-06:00", event: "customer_update_approve", summary: "Approved customer update for order 3425326" }] })) };
      else if (section === "trend") {
        const dates = query.get("interval") === "day" ? ["2026-11-05", "2026-11-06", "2026-11-07", "2026-11-08"] : ["2026-10-12", "2026-10-19", "2026-10-26", "2026-11-02"];
        data = { ...meta, interval: query.get("interval"), event_retention_days: 180, people: names.map((identity, index) => ({ identity, devices: { mobile: 320, desktop: 100, tablet: 30 }, series: dates.map((date, i) => ({ date, active_minutes: [50, 90, 65, 110][i] + index * 20, actions: 30, categories: { bol: 3 + index, checkins: 4, approvals: 5 + i, chat: 6, edits: 3, messages: 8, sync: 1, other: 2 } })) })), kof: { booker: names.map((name, index) => ({ name, series: dates.map((date, i) => ({ date, loads: 5 + i + index, profit: [100, 260, 120, 340][i] + index * 150 })) })), rep: [] }, feature_adoption: empty ? [] : dates.map((week, i) => ({ week, features: [{ feature: "assistant_question", distinct_people: i + 1 }, { feature: "customer_update_approve", distinct_people: 2 + i % 2 }] })), response_speed: empty ? [] : dates.map((week, i) => ({ week, people: names.map(identity => ({ identity, count: 5, median_seconds: 900 - i * 120, avg_seconds: 920 })) })) };
      }
      else if (section === "flows") data = { ...meta, transitions: empty ? [] : [{ from: "/loads", to: "/tracking", count: 42 }, { from: "/tracking", to: "/customer-updates", count: 23 }] };
      else if (section === "health") data = { ...meta, errors_per_day: Array.from({ length: 7 }, (_, i) => ({ date: "2026-11-0" + (i + 2), count: empty ? 0 : [0, 2, 1, 0, 4, 1, 0][i] })), failing_endpoints: empty ? [] : [{ method: "POST", path: "/api/kof/loads/{order_no}/messages", count: 3 }], slowest_endpoints: empty ? [] : [{ method: "POST", path: "/api/kof/sync", count: 8, p50_ms: 2400, p95_ms: 4100 }], latency_basis: "Only requests over 2s or with 5xx status are sampled; not all requests", client_errors: empty ? [] : [{ id: 1, identity: "Tony", path: "/tracking", message: "Network request interrupted", time: "2026-11-08T14:12:00-06:00" }], client_error_total: empty ? 0 : 1, failed_sends: { kof_messages: empty ? [] : [{ id: 1, order_no: 3425326, time: "2026-11-08T14:12:00-06:00" }], kof_message_total: empty ? 0 : 1, communications_status_available: false }, kof_sync: { last_success: empty ? null : "2026-11-09T01:50:00Z", freshness_seconds: empty ? null : 600, failures: empty ? 0 : 1, runs: empty ? [] : [{ id: 1, status: "ok", started_at: "2026-11-09T01:45:00Z", finished_at: "2026-11-09T01:50:00Z" }] }, llm_errors: empty ? [] : [{ identity: "Scotti", time: "2026-11-08T14:12:00-06:00", detail: { operation: "bol_extraction", error_type: "APIConnectionError" } }], llm_error_total: empty ? 0 : 1, integrations: { sms_live: true, email_live: true, assistant_live: false }, workspace_metrics_note: "KOF messages and sync runs have no actor IDs; workspace-wide regardless of exclude_admins." };
      else if (section === "features") data = { ...meta, features: [{ feature: "customer_update_approve", label: "Approved customer update", uses: empty ? 0 : 24, distinct_people: empty ? 0 : 3, last_used: empty ? null : "2026-11-08T14:12:00-06:00" }, { feature: "truckstop_post", label: "Posted to TruckStop", uses: 0, distinct_people: 0, last_used: null }] };
    }
    if (window.fixtureMode === "loading" && path.includes("/admin/usage/")) await new Promise(resolve => (window.fixtureResumeFns ??= []).push(resolve));
    return new Response(JSON.stringify(data), { status, headers: { "Content-Type": "application/json" } });
  };
}

try {
  await call("Page.enable");
  await call("Runtime.enable");
  await call("Page.addScriptToEvaluateOnNewDocument", { source: `(${fixture.toString()})()` });
  await call("Emulation.setDeviceMetricsOverride", { width: 390, height: 844, deviceScaleFactor: 1, mobile: true });
  await call("Emulation.setTimezoneOverride", { timezoneId: "Asia/Tokyo" });
  await call("Page.navigate", { url: `${origin}/usage` });

  await ready("document.body.innerText.includes('Leaderboard') && document.body.innerText.includes('Pat (never active)')");
  assert(await run("fixtureRequests.filter(r => r.path.includes('/admin/usage/')).every(r => r.path.includes('exclude_admins=true') && r.path.includes('date=2026-11-08'))"));
  await shot("usage-visuals-overview-mobile", true);
  const focus = text => run(`Array.from(document.querySelectorAll('h2,h3')).find(el => el.textContent === ${JSON.stringify(text)}).scrollIntoView({block:'start'}); window.scrollBy(0,-135)`);
  await clickTab("Live");
  await ready("document.body.innerText.includes('30s ago')");
  await focus("Who's on now");
  await shot("usage-visuals-live-mobile");
  await clickTab("People");
  await ready("document.querySelectorAll('button[aria-label^=\"Open Scotti activity\"]').length === 365 && document.body.innerText.includes('Category percentages')");
  await focus("Contribution year");
  await shot("usage-visuals-people-mobile");
  await shot("usage-visuals-people-full-mobile", true);
  await run("document.querySelector('button[aria-label^=\"Open Scotti activity for 2026-11-08\"]').click()");
  await ready("document.body.innerText.includes('Feed filtered to 2026-11-08')");
  assert(await run("fixtureRequests.some(r => r.path.includes('/feed?') && r.path.includes('period=day') && r.path.includes('date=2026-11-08') && r.path.includes('identity=Scotti'))"));
  await focus("Day swimlanes");
  await shot("usage-visuals-activity-mobile");
  await run(`document.querySelector('[aria-label="Day timeline; scroll horizontally"]').scrollLeft=280`);
  await shot("usage-visuals-activity-actions-mobile");
  await run("document.querySelector('[aria-label=\"Previous timeline day\"]').click()");
  await ready("fixtureRequests.some(r => r.path.includes('/timeline?') && r.path.includes('date=2026-11-07'))");
  await clickTab("Trends");
  await ready("document.querySelectorAll('svg[aria-label*=\"over time\"]').length >= 2");
  await focus("Active time by person");
  await shot("usage-visuals-trends-mobile");
  await shot("usage-visuals-trends-full-mobile", true);
  await run("document.querySelector('[aria-label=\"Trend range\"]').value='365'; document.querySelector('[aria-label=\"Trend range\"]').dispatchEvent(new Event('change',{bubbles:true})); document.querySelector('[aria-label=\"Trend interval\"]').value='day'; document.querySelector('[aria-label=\"Trend interval\"]').dispatchEvent(new Event('change',{bubbles:true}))");
  await ready("fixtureRequests.some(r => r.path.includes('/trend?') && r.path.includes('days=365') && r.path.includes('interval=day'))");
  await clickTab("Output");
  await ready("document.body.innerText.includes('$42,000') && document.body.innerText.includes('12m median')");
  assert.equal(await run("document.documentElement.scrollWidth > 390"), false);
  await clickTab("Features");
  await ready("document.body.innerText.includes('/loads → /tracking') && document.body.innerText.includes('Unused')");
  await clickTab("Health");
  await ready("document.body.innerText.includes('p95 4100ms') && document.body.innerText.includes('APIConnectionError')");
  await focus("Errors per day");
  await shot("usage-visuals-health-mobile");
  await shot("usage-visuals-health-full-mobile", true);
  await run("fixtureMode='empty'; document.querySelector('[aria-label=\"Previous period\"]').click()");
  await ready("document.body.innerText.includes('No errors recorded in this period.')");
  for (const [tab, text] of [["Live", "Nobody is active right now."], ["People", "No people with recorded activity."], ["Activity", "No activity on this day."], ["Trends", "No activity to chart."], ["Output", "No KOF output in this period."], ["Features", "No page transitions recorded."]]) {
    await clickTab(tab);
    await ready(`document.body.innerText.includes(${JSON.stringify(text)})`);
    assert.equal(await run("document.documentElement.scrollWidth > 390"), false, tab + " empty state overflow");
  }
  await clickTab("Health");
  await run("fixtureMode='loading'; document.querySelector('[aria-label=\"Previous period\"]').click()");
  await ready("document.body.innerText.includes('Loading errors per day')");
  await run("fixtureMode='normal'; fixtureResumeFns.forEach(resolve=>resolve()); fixtureResumeFns=[]");
  await ready("document.body.innerText.includes('p95 4100ms')");
  await run("fixtureMode='error'; document.querySelector('[aria-label=\"Previous period\"]').click()");
  await ready("document.body.innerText.includes('Analytics temporarily unavailable')");
  await run("fixtureMode='normal'; Array.from(document.querySelectorAll('button')).find(el=>el.textContent==='Retry').click()");
  await ready("document.body.innerText.includes('p95 4100ms') && !document.querySelector('main [role=status]')");
  await run("sessionStorage.setItem('analytics-fixture-role','member')");
  await call("Page.reload");
  await ready("location.pathname === '/dashboard' && fixtureRequests.some(r => r.path === '/api/auth/me')");
  assert.equal(await run("fixtureRequests.some(r => r.path.includes('/admin/usage/'))"), false);
  console.log("390px Usage visuals passed: Live, contribution grid/radar/devices, date/person drilldown, swimlanes, trend controls, output, flows, health; normal/empty/loading/error/retry, member redirect, broker timezone and no page overflow. Screenshots saved.");
} finally {
  ws.close();
}
