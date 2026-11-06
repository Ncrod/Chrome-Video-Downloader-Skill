#!/usr/bin/env python3
"""Downloads the videos found by capture.mjs into a folder of the user's choice (no cloud upload).

usage: python download.py --jobs jobs.captured.json --out "D:/Videos/Curso" [--parallel 3] [--fragments 8]

Fast by design (the same ideas as the browser extension it was modelled on):
  * several videos at once (--parallel), the SMALLEST first, so the quick ones are finished and usable
    while the big ones are still running;
  * every video downloads its HLS fragments concurrently (--fragments) through yt-dlp's native downloader.
    This needs `pycryptodomex` for AES-128 streams (pip install pycryptodomex); without it yt-dlp falls
    back to ffmpeg, which fetches one fragment at a time and is several times slower.

For every job: refuses DRM (Widevine/PlayReady/FairPlay), downloads HLS/DASH/file with yt-dlp+ffmpeg,
checks the duration against expected_seconds when given, and records everything in a manifest.
Signed URLs are never written to disk by this script (only their path) and never printed.
Re-running skips videos already downloaded OK, so an interrupted batch can resume."""
import argparse, glob, json, os, re, shutil, subprocess, sys, threading, time, urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import urlsplit, urljoin

def find_bin(name):
    p = shutil.which(name)
    if p: return p
    pat = os.path.join(os.environ.get("LOCALAPPDATA", ""), "Microsoft", "WinGet", "Packages", "**", name + ".exe")
    hits = glob.glob(pat, recursive=True)
    return hits[0] if hits else None

def safe_name(s):
    s = re.sub(r'[<>:"/\\|?*\x00-\x1f]', " ", s)
    return re.sub(r"\s+", " ", s).strip(" .")[:140] or "video"

def mask(text):  # never echo signed query strings
    return re.sub(r"(https?://[^\s?\"']+)\?[^\s\"']+", r"\1?…", text)

def fetch(url, headers, limit=2_000_000):
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read(limit).decode("utf-8", "replace")

DRM = re.compile(r"widevine|playready|fairplay|urn:uuid:edef8ba9|urn:uuid:9a04f079|com\.apple\.streamingkeydelivery|skd://", re.I)

def inspect_manifest(url, headers):
    """One look at the manifest: (drm_reason|None, estimated_bytes|None, duration_seconds|None).
    AES-128 (METHOD=AES-128) is NOT DRM. The size is an estimate: BANDWIDTH of the best variant x duration."""
    est = dur = None
    try:
        txt = fetch(url, headers)
        if DRM.search(txt): return "manifest declares DRM key system", None, None
        if "#EXT-X-STREAM-INF" in txt:
            best_bw, best_uri, lines = -1, None, txt.splitlines()
            for i, line in enumerate(lines):
                m = re.search(r"BANDWIDTH=(\d+)", line)
                if line.startswith("#EXT-X-STREAM-INF") and m and int(m.group(1)) > best_bw:
                    nxt = next((l for l in lines[i + 1:] if l and not l.startswith("#")), None)
                    if nxt: best_bw, best_uri = int(m.group(1)), nxt
            if best_uri:
                sub = urljoin(url, best_uri)
                subtxt = fetch(sub, headers, 8_000_000)
                if DRM.search(subtxt): return "variant playlist declares DRM key system", None, None
                dur = sum(float(x) for x in re.findall(r"#EXTINF:([\d.]+)", subtxt)) or None
                if dur: est = int(best_bw / 8 * dur)
        elif "#EXTINF" in txt:
            dur = sum(float(x) for x in re.findall(r"#EXTINF:([\d.]+)", txt)) or None
    except Exception:
        pass
    return None, est, dur

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--jobs", required=True); ap.add_argument("--out", required=True)
    ap.add_argument("--tolerance", type=float, default=0.05)
    ap.add_argument("--parallel", type=int, default=3, help="videos downloaded at the same time (default 3)")
    ap.add_argument("--fragments", type=int, default=8, help="concurrent HLS fragments per video (default 8)")
    ap.add_argument("--manifest", help="where to write manifest.json (default: inside --out)")
    a = ap.parse_args()
    ytdlp, ffmpeg, ffprobe = find_bin("yt-dlp"), find_bin("ffmpeg"), find_bin("ffprobe")
    if not (ytdlp and ffmpeg and ffprobe):
        sys.exit("Need yt-dlp, ffmpeg and ffprobe installed (winget install yt-dlp.yt-dlp Gyan.FFmpeg).")
    try:
        import Cryptodome  # noqa: F401
    except Exception:
        print("WARNING: pycryptodomex is missing, so AES-128 HLS goes through ffmpeg, one fragment at a time (slow). "
              "Fix: pip install pycryptodomex", flush=True)
    mpath = a.manifest or os.path.join(a.out, "manifest.json")
    os.makedirs(os.path.dirname(os.path.abspath(mpath)), exist_ok=True)
    manifest = json.load(open(mpath, encoding="utf8")) if os.path.exists(mpath) else {}
    jobs = json.load(open(a.jobs, encoding="utf8"))
    lock = threading.Lock()

    def save():
        json.dump(manifest, open(mpath, "w", encoding="utf8"), indent=2, ensure_ascii=False)

    def say(msg):
        with lock: print(msg, flush=True)

    # ---- plan: decide what to do with each job, and estimate sizes so we can sort small -> large
    plan = []
    for job in jobs:
        name = safe_name(job["name"]); dest = os.path.join(a.out, name + ".mp4")
        if manifest.get(name, {}).get("status") == "ok" and os.path.exists(dest):
            say(f"skip (done) {name}"); continue
        url = job.get("media_url")
        entry = {"name": job["name"], "file": os.path.basename(dest), "page": job.get("url"),
                 "media_path": urlsplit(url).path if url else None, "expected_seconds": job.get("expected_seconds"),
                 "capture_note": job.get("note")}
        if not url:
            entry["status"] = "no-media-found"; manifest[name] = entry
            say(f"NO MEDIA  {name}  ({job.get('note') or ''})"); continue
        headers = {"User-Agent": "Mozilla/5.0"}
        if job.get("referer"): headers["Referer"] = job["referer"]
        if job.get("origin"): headers["Origin"] = job["origin"]
        drm, est, dur = inspect_manifest(url, headers)
        if drm:
            entry["status"] = "drm"; entry["note"] = drm; manifest[name] = entry
            say(f"DRM, not downloading: {name} ({drm})"); continue
        entry["estimated_bytes"], entry["manifest_seconds"] = est, dur
        plan.append((est if est is not None else float("inf"), name, dest, job, headers, entry))
    save()
    plan.sort(key=lambda p: p[0])  # smallest first
    if plan:
        tot = sum(p[0] for p in plan if p[0] != float("inf"))
        say(f"{len(plan)} video(s) to download, about {tot/1e9:.2f} GB, {a.parallel} at a time, smallest first")

    def work(item):
        est, name, dest, job, headers, entry = item
        os.makedirs(a.out, exist_ok=True)  # only when there is something to save
        cmd = [ytdlp, "--ffmpeg-location", os.path.dirname(ffmpeg), "--no-progress", "--newline",
               "--hls-prefer-native", "--concurrent-fragments", str(a.fragments),
               "--fragment-retries", "10", "--retries", "5", "--merge-output-format", "mp4", "-o", dest]
        for k, v in headers.items(): cmd += ["--add-header", f"{k}:{v}"]
        cmd.append(job["media_url"])
        t0 = time.time(); say(f"start   {name}  (~{(est if est != float('inf') else 0)/1e6:.0f} MB)")
        r = subprocess.run(cmd, capture_output=True, text=True)
        if r.returncode != 0 or not os.path.exists(dest):
            entry["status"] = "failed"; entry["note"] = mask((r.stderr or r.stdout)[-300:])
            say(f"FAILED  {name}: {entry['note']}"); return name, entry
        dur = float(subprocess.run([ffprobe, "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", dest],
                                   capture_output=True, text=True).stdout.strip() or 0)
        size = os.path.getsize(dest); el = max(time.time() - t0, 0.1)
        entry.update(status="ok", bytes=size, duration_seconds=round(dur, 1))
        exp = job.get("expected_seconds")
        if exp and abs(dur - exp) > a.tolerance * exp:
            entry["status"] = "check-duration"
            entry["note"] = f"duration {dur:.0f}s vs expected {exp}s: verify this is the right video"
        if job.get("id_match") is False and entry["status"] == "ok":
            entry["status"] = "check-match"
            entry["note"] = "media URL does not contain the page's player id: verify this is the right video"
        say(f"done    {name}  {entry['status']}  {size/1e6:.0f} MB  {dur/60:.1f} min  in {el:.0f}s  ({size/1e6/el:.1f} MB/s)  {entry.get('note','')}")
        return name, entry

    with ThreadPoolExecutor(max_workers=max(1, a.parallel)) as pool:
        futures = [pool.submit(work, item) for item in plan]
        for f in as_completed(futures):
            name, entry = f.result()
            with lock:
                manifest[name] = entry; save()
    save()
    ok = sum(1 for e in manifest.values() if e.get("status") == "ok")
    say(f"Manifest: {mpath}  ({ok}/{len(manifest)} ok)")

if __name__ == "__main__":
    main()
