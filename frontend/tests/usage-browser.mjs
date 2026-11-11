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
      if (window.fixtureMode === "error" && section === "features") { status = 503; data = { detail: "Analytics temporarily unavailable" }; }
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
      else if (section === "features") data = { ...meta, features: [{ feature: "customer_update_approve", label: "Approved customer update", uses: empty ? 0 : 24, distinct_people: empty ? 0 : 3, last_used: empty ? null : "2026-11-08T14:12:00-06:00" }, { feature: "truckstop_post", label: "Posted to TruckStop", uses: 0, distinct_people: 0, last_used: null }] };
    }
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
  await ready("document.body.innerText.includes('Leaderboard') && document.body.innerText.includes('Scotti') && !document.body.innerText.includes('Loading activity')");
  assert(await run("fixtureRequests.filter(r => r.path.includes('/admin/usage/')).every(r => r.path.includes('exclude_admins=true') && r.path.includes('date=2026-11-08'))"));
  await run("window.dispatchEvent(new Event('keydown')); tickHeartbeat()");
  assert(await run("fixtureRequests.some(r => r.path === '/api/usage/heartbeat' && JSON.parse(r.body).path === '/usage')"));
  await shot("usage-analytics-overview-mobile-full-fixture", true);
  await run("window.scrollTo(0,500)");
  await shot("usage-analytics-overview-mobile-fixture");
  await clickTab("People");
  await ready("document.body.innerText.includes('Top pages') && document.body.innerText.includes('6:05')");
  await run("window.scrollTo(0,0)");
  await shot("usage-analytics-people-mobile-full-fixture", true);
  await run("Array.from(document.querySelectorAll('main button')).find(el => el.textContent.includes('Scotti') && el.textContent.includes('Activity')).scrollIntoView({block:'start'}); window.scrollBy(0,-20)");
  await shot("usage-analytics-people-mobile-fixture");
  await run("Array.from(document.querySelectorAll('main button')).find(el => el.textContent.includes('Tony') && el.textContent.includes('Activity')).click()");
  await ready("document.body.innerText.includes('Recent activity') && !document.body.innerText.includes('Loading activity')");
  assert.equal(await run("document.querySelector('main select').value"), "Tony");
  assert(await run("fixtureRequests.some(r => r.path.includes('/feed?') && r.path.includes('identity=Tony'))"));
  assert(await run("document.body.innerText.includes('Did BOL #90123 get loaded?')"));
  await run("Array.from(document.querySelectorAll('h2')).find(el => el.textContent === 'Recent activity').scrollIntoView({block:'start'}); window.scrollBy(0,-180)");
  await shot("usage-analytics-activity-mobile-fixture");
  await run("document.querySelector('main select').value = ''; document.querySelector('main select').dispatchEvent(new Event('change', {bubbles:true}))");
  await ready("Array.from(document.querySelectorAll('button')).some(el => el.textContent === 'Load more')");
  await run("Array.from(document.querySelectorAll('button')).find(el => el.textContent === 'Load more').click()");
  await ready("!Array.from(document.querySelectorAll('button')).some(el => el.textContent === 'Load more')");
  assert(await run("fixtureRequests.some(r => r.path.includes('offset=50'))"));
  await clickTab("When");
  await ready("!!document.querySelector('table td[aria-label]')");
  await run("window.scrollTo(0,0)");
  await shot("usage-analytics-when-mobile-full-fixture", true);
  await run("Array.from(document.querySelectorAll('h2')).find(el => el.textContent === 'When the team is active').scrollIntoView({block:'start'}); window.scrollBy(0,-20)");
  await shot("usage-analytics-when-mobile-fixture");
  const totalHeat = await run("Array.from(document.querySelectorAll('table td')).reduce((sum, el) => sum + Number(el.textContent.replace('·','0')), 0)");
  await run("document.querySelector('main select').value = 'Tony'; document.querySelector('main select').dispatchEvent(new Event('change', {bubbles:true}))");
  await ready("document.querySelector('main select').value === 'Tony'");
  assert((await run("Array.from(document.querySelectorAll('table td')).reduce((sum, el) => sum + Number(el.textContent.replace('·','0')), 0)")) < totalHeat);
  await clickTab("Output");
  await ready("document.body.innerText.includes('12m median') && document.body.innerText.includes('$42,000')");
  assert.equal(await run("document.documentElement.scrollWidth > 390"), false);
  await clickTab("Features");
  await ready("document.body.innerText.includes('Unused')");
  await run("document.querySelector('input[type=checkbox]').click()");
  await ready("fixtureRequests.some(r => r.path.includes('/features?') && r.path.includes('exclude_admins=false')) && !document.body.innerText.includes('Loading activity')");
  await clickTab("Overview");
  await ready("document.body.innerText.includes('Jadin') && !document.body.innerText.includes('Loading activity')");
  await run("fixtureMode='empty'; document.querySelector('[aria-label=\"Previous period\"]').click()");
  await ready("document.body.innerText.includes('No activity in this period.')");
  assert.equal(await run("document.querySelector('[aria-label=\"Next period\"]').disabled"), false);
  await clickTab("People");
  await ready("document.body.innerText.includes('No activity in this period.') && !document.body.innerText.includes('Loading activity')");
  await clickTab("Activity");
  await ready("document.body.innerText.includes('No questions in loaded activity.')");
  await clickTab("When");
  await ready("document.body.innerText.includes('No active minutes in this period for this selection.')");
  await clickTab("Output");
  await ready("document.body.innerText.includes('No KOF output in this period.') && document.body.innerText.includes('No linked approvals in this period.')");
  await run("fixtureMode='error'");
  await clickTab("Features");
  await ready("document.body.innerText.includes('Analytics temporarily unavailable')");
  await run("fixtureMode='normal'; Array.from(document.querySelectorAll('button')).find(el => el.textContent === 'Retry').click()");
  await ready("document.body.innerText.includes('Posted to TruckStop')");
  await run("sessionStorage.setItem('analytics-fixture-role','member')");
  await call("Page.reload");
  await ready("location.pathname === '/dashboard' && fixtureRequests.some(r => r.path === '/api/auth/me')");
  assert.equal(await run("fixtureRequests.some(r => r.path.includes('/admin/usage/'))"), false);
  await run("window.dispatchEvent(new Event('touchstart')); tickHeartbeat()");
  assert(await run("fixtureRequests.some(r => r.path === '/api/usage/heartbeat' && JSON.parse(r.body).path === '/dashboard')"));
  console.log("390px Usage fixtures passed: Overview/People/Activity/When screenshots; timezone-correct anchors, admin exclusion toggle, person-to-feed filter, questions, pagination, total/person heatmaps, output, unused features, empty states, error/retry, member redirect and heartbeat.");
} finally {
  ws.close();
}
