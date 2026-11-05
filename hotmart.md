# Hotmart Club notes (verified on a real course)

- Course URL: `https://hotmart.com/es/club/<club>/products/<productId>`; each route (ruta) is
  `/track/<id>`; each lesson opens at `/content/<id>?track=<id>`.
- The player is an iframe `cf-embed.play.hotmart.com/embed/<videoId>`. The manifest is HLS on
  `vod-akm.play.hotmart.com/video/<videoId>/hls/master-pkg-*.m3u8` with a signed query; the key is
  `contentplayer.hotmart.com/.../key/*.key`. It is **AES-128 HLS, not DRM** (the stream used was ~1080p, ~1.5 Mbps).
- Referer `https://cf-embed.play.hotmart.com/` is passed automatically by capture.mjs.
- The lesson sidebar lists the lessons of the route with their durations, but the lesson currently playing shows
  "Tocando ahora" instead of its duration: read durations from a different lesson or from the downloaded file.
- Non-video items (text/PDF lessons) have no media request: they come out as `MISS`, which is expected.
- The API (`api-club-course-consumption-gateway…`) needs a bearer token: do not chase it; read the lesson list
  from the rendered page instead.
