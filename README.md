# Chrome Video Downloader Skill

A [Claude Code](https://claude.com/claude-code) skill that downloads videos from web pages **you own or are
authorized to download** (your own courses, client work, public domain) into a local folder you choose.
No cloud upload, no database.

It finds the real stream URL (HLS `.m3u8`, DASH `.mpd` or a plain video file) by watching the network of a
Chrome window through the DevTools Protocol, including players inside cross-origin iframes, then downloads it
with `yt-dlp` + `ffmpeg` and checks each video (duration against the lesson list, plus frames you can inspect).
Verified on Hotmart Club (HLS with AES-128, which is not DRM). See [`hotmart.md`](hotmart.md).

## Install

```bash
npx skills add https://github.com/Ncrod/Chrome-Video-Downloader-Skill
```

or copy this folder to `~/.claude/skills/chrome-video-downloader-skill/`.

Requirements: Node 22+, Python 3, [`yt-dlp`](https://github.com/yt-dlp/yt-dlp) and
[`ffmpeg`](https://ffmpeg.org) (Windows: `winget install yt-dlp.yt-dlp Gyan.FFmpeg`), Google Chrome.

## Use

Ask Claude, for example: *"Download my course from <url> into `D:\Videos\Course`."* Claude will:

1. Open a separate Chrome window with remote debugging (your normal Chrome is untouched). **You log in there.**
2. List the lessons and capture each stream (`scripts/capture.mjs`).
3. Download them (`scripts/download.py`), resumable, with a `manifest.json` (status, size, duration per video).
4. Verify titles against the videos and report what is ok, failed, or needs a look.

## Rules built in

- Only content you own or are authorized to download.
- **DRM is never bypassed.** Manifests declaring Widevine / PlayReady / FairPlay are skipped and reported.
- Signed URLs and tokens are never printed or written to the output folder. The temporary
  `jobs.captured.json` contains them: do not share or commit it (it is in `.gitignore`).
- Capture is read-only: it keeps media URLs only, never cookies, header values or response bodies.

## Limits

Tested only on Hotmart; other sites (Vimeo, Bunny, Cloudflare Stream...) use the same logic but are unverified.
Signed URLs expire, so download right after capturing. Sites that need cookies for the manifest or key may
return 403.

## Español (resumen)

Skill para Claude Code que descarga videos de páginas web **propias o autorizadas** a una carpeta local.
Captura la URL real del stream desde un Chrome con depuración (también dentro de iframes), descarga con
`yt-dlp` + `ffmpeg` y verifica cada video. No sube nada a la nube y **no evade DRM**. Instalación:
`npx skills add https://github.com/Ncrod/Chrome-Video-Downloader-Skill`.
