# ShortPulse

Open-source AI video agent that turns a topic or script into a ready-to-post
vertical video (1080x1920, TikTok/Reels/Shorts). Runs on your own machine —
no subscription, no paid API.

<p align="center">
  <img src="docs/demo.gif" alt="A five-second excerpt of a finished render: stock footage with word-by-word captions burning in" width="280">
</p>

<p align="center">
  <sub>
    Five seconds of one finished render, unedited — topic in, this out. The
    captions highlight a word at a time because faster-whisper timed them per
    word, which is the difference between this and a subtitle track.
    <a href="https://shortpulse.app/#examples">Sixteen more, in nine languages</a>.
  </sub>
</p>

**What "local" means here, precisely:** scripting (Ollama), voiceover
(Piper), transcription (faster-whisper), image/video generation
(SDXL/RealVisXL/LTX-Video) and rendering (FFmpeg) all run offline on your
hardware. The only stage that reaches the network is the `stock_media`
visual mode, which fetches footage from Pexels — pick another visual mode
and the whole pipeline is offline after the one-time model downloads.

Give it a topic (or your own script), and it will:

1. Break it into a punchy, high-retention scene script (Ollama or OpenAI).
2. Synthesize voiceover per scene (Piper, local MIT-licensed voices).
3. Transcribe word-level timing (`faster-whisper`) for karaoke-style captions.
4. Generate visuals per scene — AI stills + Ken Burns, local AI video, or free
   stock footage.
5. Assemble everything with FFmpeg: burned-in subtitles, background music with
   auto-ducking, an optional branded closing card, and a final `.mp4`.

Extras:
- **9 languages** — English, Turkish, Spanish, French, German, Portuguese,
  Arabic, Russian, Italian. The script, voiceover and subtitles are produced
  in the chosen language; image prompts stay in English, which is what the
  diffusion models respond to best. Voices download on first use from
  `rhasspy/piper-voices` (~60MB each).
- **Video length presets** — Short (~15-25s), Medium (~30-45s), Long (~60s+);
  the LLM is asked for a matching scene count per preset.
- **Background music by default** — falls back to a bundled royalty-free track
  (`backend/app/assets/music/Airport Lounge.mp3`, CC BY 3.0, see
  `ATTRIBUTION.md` next to it) if you don't supply your own `track_path`.
  Sidechain ducking drops it under the voiceover automatically.
- **Branded outro card** — optional closing card drawn locally with Pillow (no
  AI generation), so the last frame is your call-to-action rather than
  whatever the model imagined for it.
- **Synced transcript panel** — the project page highlights the scene that's
  currently playing and seeks the video when you click one.
- **Dub a video you already have** — upload footage and have the speech
  translated and spoken again in any of the nine languages, laid back over
  the original picture sentence by sentence. Nothing about the video is
  altered, so if the speaker is on camera their lips won't match the new
  language — the way dubbed video normally looks. Lip-sync is not attempted.

## Repository layout

```
backend/                  FastAPI service + rendering pipeline
  app/
    api/routes/           REST + WebSocket endpoints
    core/config.py         Settings (env vars) and per-project storage paths
    engines/                script_engine, audio_engine, subtitle_engine,
                             visual_engine, render_engine — the core pipeline
    services/               project_store, render_manager (task queue +
                             orchestration), connection_manager (WS broadcast)
    schemas/project.py      Pydantic data contracts (ProjectConfig, Scene, ...)
  tests/
frontend/                 Next.js 14 App Router UI
  app/                     Home (create) page, /project/[id] detail page
  components/              editor/, visual/, render/, ui/
  lib/                     types.ts (TS mirror of the Pydantic schemas),
                            api.ts (REST + WebSocket client), store.ts (Zustand)
```

## Requirements

- **Python 3.11+** and **Node 18+**
- **ffmpeg built with `libass`** — the subtitle burn-in step uses the `ass`
  filter. Homebrew's default `ffmpeg` formula on macOS does *not* include
  libass; install `brew install ffmpeg-full` (keg-only, won't shadow an
  existing `ffmpeg`) and point `FFMPEG_BINARY`/`FFPROBE_BINARY` in `.env` at
  `/opt/homebrew/opt/ffmpeg-full/bin/{ffmpeg,ffprobe}`.
- **[Ollama](https://ollama.com)** for local scriptwriting: `ollama pull llama3`
  (~4.7GB). Or set `ProjectConfig.llm.provider` to `openai` and supply a key.
- Disk space for models — they download on first use, not bundled. See the
  visual modes table below.

## Getting started

### Backend

```bash
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt   # runtime + the checks below
cp .env.example .env   # then edit: ffmpeg paths, DIFFUSION_DEVICE, API keys
uvicorn app.main:app --port 8000
```

Set `DIFFUSION_DEVICE` in `.env` to `cuda` (NVIDIA), `mps` (Apple Silicon), or
`cpu`.

`requirements.txt` alone is enough to *run* the backend, and is what the
Docker image installs. The three checks below live in
`requirements-dev.txt`, which pulls the runtime in with it.

The three checks CI runs, in the order it runs them:

```bash
ruff check .   # style and the obvious mistakes
mypy           # configured in pyproject.toml; takes no arguments
pytest -q      # database tests skip themselves without a database
```

`mypy` is the newest of the three and worth one sentence: it is on default
strictness rather than `--strict`, because what it is there to catch is an
attribute or enum member that does not exist and a `None` reaching a
parameter that cannot take one. Both have cost deploys here. Missing
annotations, which is most of what `--strict` reports, have not.

### Frontend

```bash
cd frontend
npm install
npm run dev
```

Open http://localhost:3000. If port 3000 is taken, Next.js falls back to 3001
or 3002 — that's fine, it's covered by the default CORS config.

If you run the backend on a port other than 8000, copy
`frontend/.env.local.example` to `frontend/.env.local` and set
`NEXT_PUBLIC_BACKEND_PORT` to match — it drives both the `/api` proxy and the
render-progress WebSocket.

## Running it in Docker

```bash
docker compose up --build
open http://localhost:8080
```

That brings up the API, the web UI, Postgres, and a reverse proxy in front
of all of them. Anonymous and free — no accounts, no billing. Renders and
the downloaded Piper/Whisper models live in a volume, so a rebuild doesn't
throw either away.

Two things worth knowing before you deploy it somewhere:

**Ollama is not in the compose file.** It wants the machine's GPU and its
own model cache, so it stays on the host and the API reaches it at
`host.docker.internal`. Point `OLLAMA_BASE_URL` wherever yours actually
runs.

**The image has no diffusion stack.** It is ~3GB installed and needs a GPU
to be worth running, so it is left out. That leaves `stock_media`, plus
`fast_hybrid` if you set `REPLICATE_API_TOKEN` — the same RealVisXL
checkpoint, generated over an API instead of on the box, at roughly $0.004
an image. `ai_video` has no such route and is refused outright: hosted
text-to-video costs more per render than the mode is priced at. Add
`requirements-diffusion.txt` and a CUDA base image to run either locally.

An unavailable mode is refused before anything is charged, rather than
quietly falling back — see `visual_engine.unavailable_reason`.

Everything is served from **one origin** on purpose. Next's rewrites don't
proxy protocol upgrades, so without something in front, the render-progress
WebSocket would need the backend exposed on a port of its own — fine
locally, awkward behind a single domain. The proxy routes `/ws` and `/api`
to the API and everything else to the UI.

## Deploying the hosted shape

### What it has to run on

A plain CPU VPS. No GPU: in this shape the script comes from OpenAI and
the `fast_hybrid` stills from Replicate rather than from local models, so
nothing that wants a graphics card is left in the container. That is the
trade the hosted shape makes — the self-hosted one keeps both on your own
hardware and pays for a GPU instead.

Measured on the running stack, one `stock_media` short:

| | |
|---|---|
| Idle, all four containers | ~150MB RAM |
| Peak during a render | ~820MB RAM in the API container |
| CPU during a render | takes every core it is given — briefly ~9 on a 10-core machine |
| Disk, images | ~2.6GB |
| Disk, Whisper + Piper models | ~525MB, downloaded on first render |
| Disk, per finished project | ~28MB |

So: **2 vCPU and 2GB is enough to serve, 4 vCPU and 4GB to render without
queueing.** RAM is not the constraint — the render is CPU-bound, and cores
are what turn into shorter renders. `MAX_CONCURRENT_RENDERS` is the knob;
past what the box has, concurrent renders all get slower instead of more
of them finishing.

Disk is the one that grows without being watched: renders are kept, at
roughly 28MB each, so 50GB holds on the order of a thousand before
anything has to be evicted.

The timings above are from an Apple Silicon machine. An x86 VPS core is
not the same core — treat the shape as the guidance and measure the first
render on the real box.

Two things are somewhere else and are not this machine's problem: Postgres
(Supabase, per `DATABASE_URL`) and scriptwriting (OpenAI). The `db`
container still starts in this shape and goes unused.

### Bringing it up

Accounts, credits and payments, on a domain:

```bash
cp .env.production.example .env               # domain + who runs it
cp backend/.env.production.example backend/.env   # keys, then fill it in
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build
```

Point an `A` record at the machine first — Caddy requests the certificate
on the first request and needs the name to already resolve.

Then check, rather than assume:

```bash
curl -s https://<your-domain>/api/health | jq .warnings
```

Every setting that is wrong in a way nothing else would report is listed
there, with what it costs: renders given away free, video links that break
on the next restart, a webhook that cannot be verified so purchases never
grant credits. An empty array is the goal, and it is worth wiring into a
deploy script — the entire list is silent by construction.

Two things that are easy to get wrong and give no error:

**`NEXT_PUBLIC_*` are compiled into the client bundle**, so they exist at
build time or not at all. Changing the domain, the Supabase project or who
operates the service means rebuilding the web image, not restarting it.

**Use Supabase's session pooler (port 5432), not the transaction pooler
(6543).** asyncpg uses prepared statements, which the transaction pooler
does not support.

## Visual modes

| Mode | Engine | First-run download | Speed per scene | Notes |
|---|---|---|---|---|
| `fast_hybrid` (default) | RealVisXL_V4.0 stills + FFmpeg Ken Burns | ~7GB | ~59s (Apple Silicon M-series) | Photorealistic. Swap to `sdxl-turbo` in `.env` for ~5s/scene at lower realism |
| `fast_hybrid` over Replicate | the same checkpoint, hosted | none | ~8s warm, ~70s cold start | For a machine with no GPU. Two scenes at once — more trips Replicate's rate limiter. Needs `REPLICATE_API_TOKEN`, ~$0.004 an image |
| `stock_media` | Pexels free API | none | ~5-10s (download-bound) | Genuinely photoreal — it's real footage. Needs a free API key |
| `ai_video` | LTX-Video (13B) | ~28GB | minutes | Local only. Real motion, but see the memory caveat below |

A mode this install cannot run is refused before the render starts, so it
is never charged for. If generation fails partway through anyway, that
scene falls back to `stock_media` and the render is re-priced by the share
of scenes that fell back.

### Hosted image generation (Replicate)

Optional, and only interesting if you want `fast_hybrid` without a GPU.
Create a token at <https://replicate.com/account/api-tokens>, put it in
`backend/.env` as `REPLICATE_API_TOKEN`, and set
`VISUAL_PROVIDER=replicate` if the machine also has torch installed and
you want the API used anyway. Set a spend limit on the token.

Leave it unset and nothing changes: the engine uses local diffusers where
they exist, and reports `fast_hybrid` as unavailable where they don't.

### Stock media setup

`stock_media` needs a free Pexels key: sign up at
https://www.pexels.com/api/ (email only, no card, takes a couple of minutes)
and put it in `backend/.env` as `PEXELS_API_KEY`.

**Attribution is a condition of the licence, not a courtesy.** Pexels'
API terms require a visible link back to Pexels from any app using the
API, and crediting the videographer where possible. The pipeline records
who shot each clip at fetch time and the project page displays it with
working links, plus a copy button — the credit doesn't travel inside the
`.mp4`, so paste it into your post description when you publish. Don't
remove that panel.

**Rate limits.** The free tier allows 200 requests/hour and 20,000/month.
One request per scene means roughly 40 videos/hour and 4,000/month before
you hit the ceiling; Pexels grants higher limits on request if you meet
their terms.

## Known limitations

These are real, measured on an Apple Silicon Mac with 32GB unified memory.
Better to know up front than to discover them mid-render:

- **`ai_video` is impractical on consumer hardware.** LTX-Video is a 13B
  parameter model; at full resolution it repeatedly exhausted swap and locked
  up the machine. It's currently pinned to 384x672 (upscaled during render) to
  fit in memory at all, and still takes minutes per scene. Treat it as
  experimental unless you have a large dedicated GPU.
- **`fast_hybrid` struggles with extremities.** Hands, feet, tentacles and
  similar "how many of these are there" subjects come out malformed fairly
  often. This is a known weakness of diffusion models at this size; raising
  step count and guidance was tested and did not help (2.5x slower, no
  measurable improvement). What did help was asking for them less: the script
  engine now tells the model to frame people in close-ups and medium shots and
  to keep hands, feet, full-body shots and lying poses out of the prompt.
  Faces are not on this list — on RealVisXL they hold up well, and the older
  claim that this mode mangles them described local diffusion.
- **Small local LLMs under-deliver on scene count.** `llama3` sometimes returns
  9 scenes when the Long preset asks for 12-15. `script_engine` retries up to
  3 times and drops malformed scenes rather than failing the whole render.
- **Stock clips don't always match the scene.** Pexels returns the closest
  match for the scene's visual prompt, which can be loose. Under heavy use the
  API also returns transient 403s.
- **Rendered files are never cleaned up automatically.** Each video leaves
  its stills, audio, subtitles and final `.mp4` under
  `backend/app/storage/projects/` — tens of megabytes per render, and
  deleting a project only removes files from that point on. Older renders,
  and anything left by a crashed session, stay until you remove them:
  `python scripts/prune_storage.py` reports what has no project behind it,
  `--delete` removes it.
- **Projects are in memory unless you set `DATABASE_URL`.** Without it,
  restarting the backend clears the project list and orphans in-flight
  renders. Point it at any Postgres (Supabase included) and projects,
  status and scripts survive restarts; migrations apply automatically at
  startup. Rendered `.mp4` files always persist on disk under
  `backend/app/storage/projects/`.
- **No Japanese voiceover.** Piper ships no Japanese voice, so Japanese is
  not offered in the language picker even though the script engine could
  write it. `edge-tts` covers it but has no commercial licence, so it isn't
  the default; set `VoiceConfig.provider` to `edge_tts` explicitly if you
  only need it for personal use.

## Status

Validated end-to-end: all three visual modes have produced real 1080x1920
H.264/AAC videos with voiceover, word-timed karaoke subtitles, ducked
background music and optional outro card. Model weights (diffusion,
LTX-Video, Whisper) download on first use via `diffusers`/`faster-whisper`.

Contributions welcome.

## Security

See [SECURITY.md](SECURITY.md) — what the code protects, what it does not,
and what must be configured before exposing it publicly.

## License

MIT — see [LICENSE](LICENSE).
