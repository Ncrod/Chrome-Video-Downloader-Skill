#!/usr/bin/env python3
"""Downloads the videos found by capture.mjs into a folder of the user's choice (no cloud upload).

usage: python download.py --jobs jobs.captured.json --out "D:/Videos/Curso" [--tolerance 0.05]

For every job: refuses DRM (Widevine/PlayReady/FairPlay), downloads HLS/DASH/file with yt-dlp+ffmpeg,
checks the duration against expected_seconds when given, and records everything in <out>/manifest.json.
Signed URLs are never written to disk by this script (only their path), and never printed.
Re-running skips videos already downloaded OK, so an interrupted batch can resume."""
import argparse, glob, json, os, re, shutil, subprocess, sys, urllib.request
from urllib.parse import urlsplit, urljoin

def find_bin(name):
    p = shutil.which(name)
    if p: return p
    pat = os.path.join(os.environ.get("LOCALAPPDATA", ""), "Microsoft", "WinGet", "Packages", "**", name + ".exe")
    hits = glob.glob(pat, recursive=True)
    return hits[0] if hits else None

def safe_name(s):
    s = re.sub(r'[<>:"/\|?*\x00-\x1f]', " ", s)
    return re.sub(r"\s+", " ", s).strip(" .")[:140] or "video"

def mask(text):  # never echo signed query strings
    return re.sub(r"(https?://[^\s?\"']+)\?[^\s\"']+", r"\1?…", text)

def fetch(url, headers):
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read(2_000_000).decode("utf-8", "replace")

DRM = re.compile(r"widevine|playready|fairplay|urn:uuid:edef8ba9|urn:uuid:9a04f079|com\.apple\.streamingkeydelivery|skd://", re.I)

def drm_check(url, headers):
    """Returns a reason string if the manifest declares DRM, else None. AES-128 (METHOD=AES-128) is NOT DRM."""
    try:
        txt = fetch(url, headers)
        if DRM.search(txt): return "manifest declares DRM key system"
        if "#EXT-X-STREAM-INF" in txt:  # master: peek at first variant
            for line in txt.splitlines():
                if line and not line.startswith("#"):
                    sub = urljoin(url, line)
                    if DRM.search(fetch(sub, headers)): return "variant playlist declares DRM key system"
                    break
    except Exception as e:
        return None
    return None

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--jobs", required=True); ap.add_argument("--out", required=True)
    ap.add_argument("--tolerance", type=float, default=0.05)
    a = ap.parse_args()
    ytdlp, ffmpeg, ffprobe = find_bin("yt-dlp"), find_bin("ffmpeg"), find_bin("ffprobe")
    if not (ytdlp and ffmpeg and ffprobe):
        sys.exit("Need yt-dlp, ffmpeg and ffprobe installed (winget install yt-dlp.yt-dlp Gyan.FFmpeg).")
    os.makedirs(a.out, exist_ok=True)
    mpath = os.path.join(a.out, "manifest.json")
    manifest = json.load(open(mpath, encoding="utf8")) if os.path.exists(mpath) else {}
    jobs = json.load(open(a.jobs, encoding="utf8"))

    for n, job in enumerate(jobs, 1):
        name = safe_name(job["name"]); key = name
        dest = os.path.join(a.out, name + ".mp4")
        if manifest.get(key, {}).get("status") == "ok" and os.path.exists(dest):
            print(f"[{n}/{len(jobs)}] skip (done) {name}"); continue
        url = job.get("media_url")
        entry = {"name": job["name"], "file": os.path.basename(dest), "page": job.get("url"),
                 "media_path": urlsplit(url).path if url else None, "expected_seconds": job.get("expected_seconds")}
        if not url:
            entry["status"] = "no-media-found"; manifest[key] = entry
            print(f"[{n}/{len(jobs)}] NO MEDIA {name}"); continue
        headers = {"User-Agent": "Mozilla/5.0"}
        if job.get("referer"): headers["Referer"] = job["referer"]
        if job.get("origin"): headers["Origin"] = job["origin"]
        reason = drm_check(url, headers)
        if reason:
            entry["status"] = "drm"; entry["note"] = reason; manifest[key] = entry
            print(f"[{n}/{len(jobs)}] DRM, not downloading: {name} ({reason})"); continue
        cmd = [ytdlp, "--ffmpeg-location", os.path.dirname(ffmpeg), "--no-progress", "--no-part",
               "--merge-output-format", "mp4", "-o", dest]
        for k, v in headers.items(): cmd += ["--add-header", f"{k}:{v}"]
        cmd.append(url)
        print(f"[{n}/{len(jobs)}] downloading {name} ...")
        r = subprocess.run(cmd, capture_output=True, text=True)
        if r.returncode != 0 or not os.path.exists(dest):
            entry["status"] = "failed"; entry["note"] = mask((r.stderr or r.stdout)[-300:]); manifest[key] = entry
            print(f"   FAILED: {entry['note']}"); continue
        dur = float(subprocess.run([ffprobe, "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", dest],
                                   capture_output=True, text=True).stdout.strip() or 0)
        entry.update(status="ok", bytes=os.path.getsize(dest), duration_seconds=round(dur, 1))
        exp = job.get("expected_seconds")
        if exp and abs(dur - exp) > a.tolerance * exp:
            entry["status"] = "check-duration"
            entry["note"] = f"duration {dur:.0f}s vs expected {exp}s: verify this is the right video"
        manifest[key] = entry
        print(f"   {entry['status']}  {entry['bytes']/1e6:.1f} MB  {dur:.0f}s  {entry.get('note','')}")
        json.dump(manifest, open(mpath, "w", encoding="utf8"), indent=2, ensure_ascii=False)
    json.dump(manifest, open(mpath, "w", encoding="utf8"), indent=2, ensure_ascii=False)
    print(f"Manifest: {mpath}")

if __name__ == "__main__":
    main()
