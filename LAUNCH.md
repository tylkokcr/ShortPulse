# Launch copy

Draft announcement text for ShortPulse. Not part of the app — delete or keep
as a scratchpad. Repo: https://github.com/tylkokcr/ShortPulse

Everything here is written to survive scrutiny: no claim below goes beyond
what's actually been run and measured. Skeptical audiences (r/LocalLLaMA,
r/selfhosted, HN) punish overselling far harder than they reward hype.

---

## Reddit — r/SideProject, r/opensource, r/selfhosted

**Title**
> I built an open-source alternative to $50/month short-form video generators — runs on your own machine

**Body**

I kept running into AI video tools for TikTok/Reels/Shorts that want
$20–50/month and still limit what you can customize. So I built one that runs
on my own hardware instead.

**ShortPulse** takes a topic (or your own script) and produces a finished
1080x1920 vertical video: AI-written scene breakdown, voiceover,
word-synced karaoke captions, visuals, background music with auto-ducking,
and an optional outro card. MIT licensed.

How it works:
- **Script** — Ollama (llama3) locally, or OpenAI if you prefer
- **Voiceover** — edge-tts, free Microsoft neural voices, 10 languages
- **Caption timing** — faster-whisper for word-level timestamps, so captions
  highlight word-by-word instead of dumping a whole line at once
- **Visuals** — three modes: photorealistic SDXL fine-tune, real stock
  footage from Pexels, or local text-to-video (LTX-Video)
- **Assembly** — FFmpeg: burned-in .ass subtitles, sidechain-ducked music

Being upfront about what it isn't:
- Not *fully* offline out of the box. edge-tts is free and needs no key, but
  it does call Microsoft's servers. Swap in Piper for a fully local pipeline.
- The default photorealistic model takes ~59s per scene on an M-series Mac.
  There's a faster model one config line away (~5s/scene, more "AI-looking").
- Local text-to-video is technically working but impractical on consumer
  hardware — LTX-Video is 13B params and repeatedly exhausted swap on a 32GB
  machine before I capped its resolution.
- Small local LLMs are inconsistent about scene counts, and diffusion models
  still can't count fingers.

All of that is in the README's "Known limitations" section too — I'd rather
you know before you clone it.

GitHub: https://github.com/tylkokcr/ShortPulse

Happy to answer anything about the pipeline.

---

## Reddit — r/LocalLLaMA (adjust: this crowd cares about the local/cloud line)

**Title**
> Local short-form video pipeline: Ollama + faster-whisper + SDXL + FFmpeg (MIT)

**Body**

Built a pipeline that goes from a one-line topic to a finished vertical video.
Most of it runs on your own hardware:

- **Local:** Ollama (llama3) for the scene script, faster-whisper for
  word-level caption timing, SDXL/RealVisXL (or LTX-Video) for visuals,
  FFmpeg for assembly
- **Not local:** default TTS is edge-tts, which is free and keyless but hits
  Microsoft's endpoint. Piper is wired in `audio_engine.py` if you want the
  whole thing offline. The optional stock-footage mode uses the Pexels API.

Measured on an M-series Mac, 32GB unified memory:
- RealVisXL @ 25 steps: ~59s/scene. SDXL-Turbo @ 4 steps: ~5s/scene.
- LTX-Video (13B): usable only after dropping to 384x672 and upscaling at
  render time. At full resolution it drove swap to zero and locked the
  machine. Documented rather than hidden.

Note on negative prompts, since it cost me an afternoon: with SDXL-Turbo at
`guidance_scale=0.0`, diffusers disables classifier-free guidance entirely,
so `negative_prompt` silently does nothing. Raising guidance to re-enable it
didn't measurably improve anatomy in my tests — just made it 2.5x slower.

MIT: https://github.com/tylkokcr/ShortPulse

---

## Product Hunt

**Tagline** (60 char max)
> Turn a topic into a TikTok-ready video, on your own machine

**Description**
> ShortPulse is an open-source AI video agent for short-form content. Give it
> a topic and it writes the script, generates the voiceover in 10 languages,
> times word-by-word karaoke captions, produces the visuals, mixes ducked
> background music, and renders a 1080x1920 MP4 — running on your own
> hardware instead of a monthly subscription. MIT licensed.

**First maker comment**
> Hey PH 👋
>
> I built this because every short-form AI video tool I tried wanted
> $20–50/month and still boxed in what I could change.
>
> ShortPulse runs the pipeline on your own machine: Ollama writes the scene
> breakdown, faster-whisper gives word-level caption timing (so captions
> highlight per word, the style that actually performs), and you pick between
> a photorealistic diffusion model, real Pexels stock footage, or local
> text-to-video for the visuals. FFmpeg does the assembly with burned-in
> subtitles and sidechain-ducked music.
>
> Two honest caveats, both in the README: the default voice uses Microsoft's
> free Edge TTS, which is keyless but not offline (Piper is wired in if you
> want fully local), and the local text-to-video mode is heavy enough that
> it's really only practical on a serious GPU.
>
> It's MIT — clone it, change the prompts, swap the models.
> Feedback very welcome.

---

## Notes before posting

- **Attach a demo video.** Far more persuasive than any of this copy. The
  stock_media renders looked the most convincing.
- **Reddit rules:** r/SideProject and r/opensource are fine with self-promo;
  many subs require a flair or restrict link posts. Check each sub's rules.
- **Timing:** Product Hunt launches are dated 12:01am PT; posting midweek is
  conventional.
- **Be ready for:** "how is this different from [X]" (answer: local + MIT +
  no subscription) and "does it actually look good" (answer: post the video).
