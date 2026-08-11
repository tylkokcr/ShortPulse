# Landing page example renders

The clips shown in the "Real output" marquee on the landing page. Every one
came out of this pipeline in `stock_media` mode — nothing here was sourced
elsewhere or touched up afterwards.

## Why the .mp4 files aren't in git

They total ~26MB, and re-encoding them churns that on every commit. The
repo tracks the `.jpg` posters (~590KB) instead, so a fresh clone still
renders the marquee with correct thumbnails; only hover-to-play is missing
until the videos exist locally.

## Regenerating them

Each clip is a normal render. With the backend running:

```bash
curl -X POST http://localhost:8000/api/projects \
  -H 'Content-Type: application/json' \
  -d '{"topic":"Why honey never spoils","visual_mode":"stock_media","video_length":"short","language":"en"}'
```

Then transcode the finished `final.mp4` down for the web — the masters are
1080x1920 and far larger than this page needs:

```bash
ffmpeg -i backend/app/storage/projects/<id>/output/final.mp4 \
  -vf "scale=640:1138:flags=lanczos" \
  -c:v libx264 -profile:v high -crf 28 -preset slow -pix_fmt yuv420p \
  -movflags +faststart -c:a aac -b:a 80k -ac 1 \
  frontend/public/examples/<slug>.mp4

ffmpeg -ss 1.5 -i backend/app/storage/projects/<id>/output/final.mp4 \
  -vframes 1 -vf "scale=560:996:flags=lanczos" -q:v 5 \
  frontend/public/examples/<slug>.jpg
```

The slugs, titles, durations and scene counts are listed in
`frontend/components/marketing/Examples.tsx`. Keep them in step with what
you actually rendered — the point of the section is that those numbers are
real.

## Attribution

The footage comes from Pexels and the videographers are credited in
`Examples.tsx`; Pexels' API terms require both that credit and a visible
link back. The background music is "Airport Lounge" by Kevin MacLeod
(incompetech.com), CC BY 3.0. If you regenerate these with different
clips, update the credits to match the new ones — the pipeline records who
shot each clip on the project's scenes.
