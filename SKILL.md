---
name: chrome-video-downloader-skill
description: Download videos from any web page the user owns or is authorized to download (course platforms like Hotmart, Vimeo, Bunny, Cloudflare/Akamai HLS, DASH, direct MP4) into a local folder of their choice. Captures the real stream URL through Chrome DevTools, even inside cross-origin iframes, then downloads with yt-dlp + ffmpeg and verifies each video. Use when the user asks to download, extract, back up or migrate their own course/lesson videos from a website. Does not upload anywhere; refuses DRM.
---

# Chrome Video Downloader

Downloads videos from web pages into **a local folder the user names**. No cloud upload, no database.
Works on any site whose player requests an HLS (`.m3u8`), DASH (`.mpd`) or plain video file. Proven on
Hotmart Club (see `hotmart.md`).

## Rules (non-negotiable)
1. **Only content the user owns or is authorized to download** (their own course, a client's, public domain).
   If ownership is unclear, ask. Do not use this to take other people's paid content.
2. **DRM stops the job.** `download.py` refuses manifests declaring Widevine / PlayReady / FairPlay and records
   `status: drm`. Never try to bypass it. Plain HLS **AES-128** (`METHOD=AES-128`) is not DRM and is fine.
3. **Never print, log or commit signed URLs or tokens.** `jobs.captured.json` holds them: keep it in a scratch
   folder, not in the user's project or the output folder. Signed URLs expire, so download right after capturing.
4. **The user logs in.** Never type passwords. Ask them to sign in inside the debug Chrome window.
5. **Ask for the output folder** if they did not give one. Do not install software without saying so
   (needs `yt-dlp`, `ffmpeg`, Node 22+; offer `winget install yt-dlp.yt-dlp Gyan.FFmpeg`).

## Workflow
1. **Debug Chrome.** `node scripts/launch-chrome.mjs --url <site>` opens a *separate* Chrome window (own profile,
   port 9222) and leaves the user's normal Chrome alone. Chrome 136+ ignores debugging on the default profile,
   so a dedicated profile is required. Ask the user to log in there and open the course.
2. **List the lessons** into `jobs.json`: `[{"name": "01 - Title", "url": "<lesson page>", "expected_seconds": 541}]`.
   Get titles, order and durations from the page (the sidebar/lesson list). Use `name` exactly as the lesson
   title, prefixed with its order number, so files sort correctly. `expected_seconds` is optional but enables
   the duration check.
3. **Capture:** `node scripts/capture.mjs --jobs jobs.json --out jobs.captured.json --seconds 20`
   Each line prints `OK hls` or `MISS`. For a `MISS`, open that lesson, press play in the debug window and retry
   just that job (some players only request the manifest after a click).
4. **Download:** `python scripts/download.py --jobs jobs.captured.json --out "<folder>"`
   Resumable (skips `status: ok`). Writes `<folder>/manifest.json` with size, duration and status per video.
5. **Verify, do not assume.** For each video: statuses must be `ok`; `check-duration` means the length differs
   from the list by more than 5% (maybe the wrong video, or the list belongs to the neighbouring lesson, as
   happened on Hotmart where "Tocando ahora" hides the current duration). Extract a frame near the start and
   one near the end (`ffmpeg -ss N -i f.mp4 -frames:v 1 f.jpg`) and look at them next to the lesson title and
   its poster. Report anything doubtful to the user; do not silently accept it.
6. **Report:** how many ok / drm / failed / check-duration, total size in the folder, and anything to redo.

## Notes
- Capture is read-only: it only keeps media URLs, never cookies, header values or bodies.
- Many lessons can be large (about 11 MB/min at 1080p). State the total size before a big batch.
- If a site needs cookies for the key or manifest, yt-dlp may fail with 403: tell the user rather than
  extracting their cookies; `--cookies-from-browser` is the user's call.
- Close the debug Chrome window when done (profile folder stays for next time).
