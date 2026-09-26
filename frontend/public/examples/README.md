# Example renders

The clips shown in the "Real output" marquee on the landing page, and the
four in the studio's "start from an example" strip. Every one came out of
this pipeline in `stock_media` mode — nothing here was sourced elsewhere
or touched up afterwards.

## Two shapes, and which goes where

The `-sq` files are 1:1 (1080x1080 masters, 640x640 on the page); the rest
are 9:16. The split is not cosmetic:

- **The marquee shows the vertical ones.** That page sells what the
  product makes, and what it makes by default is 9:16.
- **The studio strip shows the square ones.** It sits above the form on a
  working screen, and four vertical clips made the row as tall as the form
  itself — you scrolled past a band of letterbox slivers to reach the
  topic field.

`Example.square` in `frontend/lib/examples.ts` is what keeps them apart;
the marquee filters on it and the studio's `PICKED` names the square
slugs.

## Why the .mp4 files aren't in git

They total ~34MB, and re-encoding them churns that on every commit. The
repo tracks the `.jpg` posters (~590KB) instead, so a fresh clone still
renders the marquee with correct thumbnails; only hover-to-play is missing
until the videos exist locally.

## Getting them onto the deployment — the step that is easy to miss

The consequence of the above is that **a deploy cannot ship these**. The
server builds the web image from its git checkout, the checkout obeys the
same ignore rule, so `docker compose up --build web` produces an image
with eleven posters and no videos. Every clip 404s and the marquee is a
row of stills that never play, which is exactly what the live site did
from launch until someone checked.

They have to be copied to the server before the build, and again after any
`git clean`:

```bash
scp frontend/public/examples/*.mp4 \
    shortpulse:/opt/shortpulse/frontend/public/examples/
ssh shortpulse 'cd /opt/shortpulse && \
    docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build web'
```

Verify rather than assume — a 404 here looks like nothing at all:

```bash
curl -s -o /dev/null -w '%{http_code}\n' https://<your-domain>/examples/honey.mp4
```

## Regenerating them

Each clip is a normal render. With the backend running:

```bash
curl -X POST http://localhost:8000/api/projects \
  -H 'Content-Type: application/json' \
  -d '{"topic":"Why honey never spoils","visual_mode":"stock_media","video_length":"short","language":"en"}'
```

A square one is the same call with `"aspect_ratio": "1:1"` added.

Then transcode the finished `final.mp4` down for the web — the masters are
1080x1920 (or 1080x1080) and far larger than this page needs. Note
`-nostdin`: without it ffmpeg eats the loop's input and you get files named
`uiet-sq.mp4`.

```bash
# 9:16 — use scale=640:640 and 560:560 for a square one.
ffmpeg -nostdin -i backend/app/storage/projects/<id>/output/final.mp4 \
  -vf "scale=640:1138:flags=lanczos" \
  -c:v libx264 -profile:v high -crf 28 -preset slow -pix_fmt yuv420p \
  -movflags +faststart -c:a aac -b:a 80k -ac 1 \
  frontend/public/examples/<slug>.mp4

ffmpeg -ss 1.5 -i backend/app/storage/projects/<id>/output/final.mp4 \
  -vframes 1 -vf "scale=560:996:flags=lanczos" -q:v 5 \
  frontend/public/examples/<slug>.jpg
```

The slugs, titles, durations and scene counts are listed in
`frontend/lib/examples.ts`. Keep them in step with what
you actually rendered — the point of the section is that those numbers are
real.

## Attribution

The footage comes from Pexels and the videographers are credited in
`Examples.tsx`; Pexels' API terms require both that credit and a visible
link back. The background music is "Airport Lounge" by Kevin MacLeod
(incompetech.com), CC BY 3.0. If you regenerate these with different
clips, update the credits to match the new ones — the pipeline records who
shot each clip on the project's scenes.
