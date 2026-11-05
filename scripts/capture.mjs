// Finds the real media manifest (HLS .m3u8 / DASH .mpd / direct file) that a page's player requests,
// including players inside cross-origin iframes, by watching the network through Chrome DevTools Protocol.
// Read-only: it never reads cookies, headers' secret values or response bodies; it only keeps media URLs.
//
// usage:
//   node capture.mjs --jobs jobs.json --out jobs.captured.json [--port 9222] [--seconds 20]
//   node capture.mjs --url <page url> --name "Title" --out jobs.captured.json
// jobs.json: [{ "name": "01 Bienvenida", "url": "<lesson page url>", "expected_seconds": 541 }, ...]
// Output keeps the same fields plus media_url / kind / referer / origin. Signed URLs EXPIRE: download soon after.
import { writeFileSync, readFileSync } from "node:fs";

const arg = (n, d) => { const i = process.argv.indexOf(`--${n}`); return i > 0 ? process.argv[i + 1] : d; };
const port = arg("port", "9222");
const seconds = Number(arg("seconds", "20"));
const out = arg("out", "jobs.captured.json");
const jobs = arg("jobs")
  ? JSON.parse(readFileSync(arg("jobs"), "utf8"))
  : [{ name: arg("name", "video"), url: arg("url") }];
if (!jobs.length || !jobs[0].url) { console.error("Need --jobs file or --url"); process.exit(1); }

const PLAY = "document.querySelectorAll('video').forEach(v=>{v.muted=true;v.play&&v.play().catch(()=>{})})";
const MEDIA = /\.(m3u8|mpd|mp4|webm|m4v|mov)(\?|$)/i;
const MIME = /mpegurl|dash\+xml|^video\//i;
const SEGMENT = /\.(ts|m4s|aac|m4a)(\?|$)/i;

const targets = await (await fetch(`http://127.0.0.1:${port}/json`)).json();
const page = targets.find(t => t.type === "page" && /^https?:/.test(t.url));
if (!page) { console.error("No http(s) page open in the debug Chrome."); process.exit(1); }

const ws = new WebSocket(page.webSocketDebuggerUrl);
await new Promise((res, rej) => { ws.onopen = res; ws.onerror = rej; });
let id = 0; const pending = new Map(); let found = [];
const send = (method, params = {}, sessionId) => new Promise(res => {
  const mid = ++id; pending.set(mid, res);
  ws.send(JSON.stringify({ id: mid, method, params, ...(sessionId ? { sessionId } : {}) }));
});
const reqInfo = new Map();
ws.onmessage = async ev => {
  const m = JSON.parse(ev.data);
  if (m.id && pending.has(m.id)) { pending.get(m.id)(m.result); pending.delete(m.id); return; }
  if (m.method === "Target.attachedToTarget") {
    const s = m.params.sessionId;
    await send("Network.enable", {}, s);
    await send("Target.setAutoAttach", { autoAttach: true, waitForDebuggerOnStart: false, flatten: true }, s);
    await send("Runtime.runIfWaitingForDebugger", {}, s);
    // frames with their own session (cross-origin iframes): start their muted player too
    setTimeout(() => send("Runtime.evaluate", { expression: PLAY }, s), 2500);
  }
  if (m.method === "Network.requestWillBeSent") {
    const u = m.params.request.url;
    if (SEGMENT.test(u)) return;
    const h = m.params.request.headers || {};
    reqInfo.set(m.params.requestId, { url: u, referer: h.Referer || h.referer || "", origin: h.Origin || h.origin || "" });
    if (MEDIA.test(u)) found.push({ url: u, referer: h.Referer || h.referer || "", origin: h.Origin || h.origin || "" });
  }
  if (m.method === "Network.responseReceived") {
    const mime = m.params.response.mimeType || "";
    const r = reqInfo.get(m.params.requestId);
    if (r && MIME.test(mime) && !found.some(f => f.url === r.url)) found.push(r);
  }
};

await send("Network.enable");
await send("Page.enable");
await send("Target.setAutoAttach", { autoAttach: true, waitForDebuggerOnStart: false, flatten: true });

const kindOf = u => /\.m3u8/i.test(u) ? "hls" : /\.mpd/i.test(u) ? "dash" : "file";
const rank = f => (/master/i.test(f.url) ? 0 : 1) + (kindOf(f.url) === "hls" ? 0 : kindOf(f.url) === "dash" ? 2 : 4);
const result = [];
for (const job of jobs) {
  found = []; reqInfo.clear();
  await send("Page.navigate", { url: job.url });
  await new Promise(r => setTimeout(r, 4000));
  // muted autoplay so the player requests its manifest; applies to the main frame and attached frames
  await send("Runtime.evaluate", { expression: PLAY });
  const end = Date.now() + seconds * 1000;
  while (Date.now() < end && !found.length) await new Promise(r => setTimeout(r, 500));
  await new Promise(r => setTimeout(r, 1500));
  const best = [...found].sort((a, b) => rank(a) - rank(b))[0];
  result.push({ ...job, media_url: best?.url ?? null, kind: best ? kindOf(best.url) : null,
    referer: best?.referer ?? "", origin: best?.origin ?? "", candidates: found.length });
  console.log(`${best ? "OK  " : "MISS"} ${job.name}  ${best ? kindOf(best.url) : "no media request seen"}`);
}
writeFileSync(out, JSON.stringify(result, null, 2));
console.log(`Wrote ${out} (contains signed URLs: do not share or commit).`);
ws.close(); process.exit(0);
