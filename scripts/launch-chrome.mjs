// Launches a SEPARATE Chrome window (own profile) with remote debugging, so the user's normal
// Chrome stays untouched. Chrome 136+ ignores --remote-debugging-port on the default profile,
// which is why a dedicated --user-data-dir is required. The user logs in to sites in that window.
// usage: node launch-chrome.mjs [--port 9222] [--profile <dir>] [--url <start url>]
import { spawn } from "node:child_process";
import { existsSync } from "node:fs";
import { homedir } from "node:os";
import { join } from "node:path";

const arg = (n, d) => { const i = process.argv.indexOf(`--${n}`); return i > 0 ? process.argv[i + 1] : d; };
const port = arg("port", "9222");
const profile = arg("profile", join(homedir(), "chrome-debug-profile"));
const url = arg("url", "about:blank");

const candidates = [
  process.env.CHROME_PATH,
  "C:/Program Files/Google/Chrome/Application/chrome.exe",
  "C:/Program Files (x86)/Google/Chrome/Application/chrome.exe",
  "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
  "/usr/bin/google-chrome", "/usr/bin/chromium", "/usr/bin/chromium-browser",
].filter(Boolean);
const chrome = candidates.find(p => existsSync(p));
if (!chrome) { console.error("Chrome not found. Set CHROME_PATH."); process.exit(1); }

try {
  const r = await fetch(`http://127.0.0.1:${port}/json/version`);
  if (r.ok) { console.log(`Already listening on ${port}.`); process.exit(0); }
} catch {}

spawn(chrome, [`--remote-debugging-port=${port}`, `--user-data-dir=${profile}`, "--no-first-run", url],
  { detached: true, stdio: "ignore" }).unref();

for (let i = 0; i < 30; i++) {
  await new Promise(r => setTimeout(r, 500));
  try { if ((await fetch(`http://127.0.0.1:${port}/json/version`)).ok) { console.log(`Chrome ready on port ${port}, profile ${profile}`); process.exit(0); } } catch {}
}
console.error("Chrome did not open the debugging port."); process.exit(1);
