# ShortPulse

Open-source AI video agent that turns a topic or script into a ready-to-post
vertical video (1080x1920, TikTok/Reels/Shorts). Runs on your own machine —
no subscription, no paid API.

**What "local" means here, precisely:** scripting (Ollama), transcription
(faster-whisper), image/video generation (SDXL/RealVisXL/LTX-Video) and
rendering (FFmpeg) all run offline on your hardware. Two things reach the
network by default: `edge-tts` uses Microsoft's free Edge voices
(`speech.platform.bing.com` — no key, no account, but it *is* a network
call), and the `stock_media` visual mode obviously fetches from Pexels. For
a fully offline pipeline, switch `VoiceConfig.provider` to `piper` (a local
ONNX voice) and avoid `stock_media`.

Give it a topic (or your own script), and it will:

1. Break it into a punchy, high-retention scene script (Ollama or OpenAI).
2. Synthesize voiceover per scene (`edge-tts`, free neural voices).
3. Transcribe word-level timing (`faster-whisper`) for karaoke-style captions.
4. Generate visuals per scene — AI stills + Ken Burns, local AI video, or free
   stock footage.
5. Assemble everything with FFmpeg: burned-in subtitles, background music with
   auto-ducking, an optional branded closing card, and a final `.mp4`.

Extras:
- **10 languages** — English, Turkish, Spanish, French, German, Portuguese,
  Japanese, Arabic, Russian, Italian. The script, voiceover and subtitles are
  produced in the chosen language; image prompts stay in English, which is
  what the diffusion models respond to best.
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
pip install -r requirements.txt
cp .env.example .env   # then edit: ffmpeg paths, DIFFUSION_DEVICE, API keys
uvicorn app.main:app --port 8000
```

Set `DIFFUSION_DEVICE` in `.env` to `cuda` (NVIDIA), `mps` (Apple Silicon), or
`cpu`.

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

## Visual modes

| Mode | Engine | First-run download | Speed per scene | Notes |
|---|---|---|---|---|
| `fast_hybrid` (default) | RealVisXL_V4.0 stills + FFmpeg Ken Burns | ~7GB | ~59s (Apple Silicon M-series) | Photorealistic. Swap to `sdxl-turbo` in `.env` for ~5s/scene at lower realism |
| `stock_media` | Pexels free API | none | ~5-10s (download-bound) | Genuinely photoreal — it's real footage. Needs a free API key |
| `ai_video` | LTX-Video (13B) | ~28GB | minutes | Real motion, but see the memory caveat below |

Visual generation automatically falls back to `stock_media` if the selected
local mode fails — so a missing GPU degrades gracefully rather than erroring.

### Stock media setup

`stock_media` needs a free Pexels key: sign up at
https://www.pexels.com/api/ (email only, no card, takes a couple of minutes)
and put it in `backend/.env` as `PEXELS_API_KEY`.

## Known limitations

These are real, measured on an Apple Silicon Mac with 32GB unified memory.
Better to know up front than to discover them mid-render:

- **`ai_video` is impractical on consumer hardware.** LTX-Video is a 13B
  parameter model; at full resolution it repeatedly exhausted swap and locked
  up the machine. It's currently pinned to 384x672 (upscaled during render) to
  fit in memory at all, and still takes minutes per scene. Treat it as
  experimental unless you have a large dedicated GPU.
- **`fast_hybrid` struggles with counting.** Hands, tentacles, and similar
  "how many of these are there" subjects come out malformed fairly often. This
  is a known weakness of diffusion models at this size; raising step count and
  guidance was tested and did not help (2.5x slower, no measurable
  improvement).
- **Small local LLMs under-deliver on scene count.** `llama3` sometimes returns
  9 scenes when the Long preset asks for 12-15. `script_engine` retries up to
  3 times and drops malformed scenes rather than failing the whole render.
- **Stock clips don't always match the scene.** Pexels returns the closest
  match for the scene's visual prompt, which can be loose. Under heavy use the
  API also returns transient 403s.
- **Projects are stored in memory.** Restarting the backend clears the project
  list and cancels in-flight renders. Finished `.mp4` files persist on disk
  under `backend/app/storage/projects/`.
- **Default TTS is not offline.** `edge-tts` is free and keyless but calls
  Microsoft's servers. `piper` and `coqui_xtts` providers are wired in
  `audio_engine.py` for a fully offline setup, but they need their own
  model/binary installed and have not been exercised as thoroughly as the
  edge-tts path.

## Status

Validated end-to-end: all three visual modes have produced real 1080x1920
H.264/AAC videos with voiceover, word-timed karaoke subtitles, ducked
background music and optional outro card. Model weights (diffusion,
LTX-Video, Whisper) download on first use via `diffusers`/`faster-whisper`.

Contributions welcome.

## License

MIT — see [LICENSE](LICENSE).
