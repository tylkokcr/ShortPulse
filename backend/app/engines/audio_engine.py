"""Audio & subtitle-timing engine.

Two responsibilities:
  1. Synthesize voiceover audio per scene with `edge-tts` (free, no API key,
     good quality neural voices). Piper/XTTS are wired as alternate
     providers for fully-offline or voice-cloning use cases.
  2. Run `faster-whisper` over the synthesized audio to extract word-level
     timestamps, which the subtitle engine uses to build karaoke-style
     highlight animations.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path

from app.schemas.project import Scene, Segment, TTSProvider, VoiceConfig, Word

logger = logging.getLogger(__name__)

# faster-whisper loads a multi-hundred-MB model; keep a process-wide cache
# so every scene transcription doesn't reload it from disk.
_whisper_model_cache: dict[str, object] = {}

_EMOJI_PATTERN = re.compile(
    "["
    "\U0001F300-\U0001FAFF"  # pictographs, transport, symbols, emoticons v2+
    "\U00002600-\U000027BF"  # misc symbols & dingbats
    "\U0001F1E6-\U0001F1FF"  # regional indicator symbols (flags)
    "\U0001F900-\U0001F9FF"  # supplemental symbols & pictographs
    "️"  # variation selector-16
    "‍"  # zero-width joiner (composite emoji)
    "]+",
    flags=re.UNICODE,
)


def clean_text_for_tts(text: str) -> str:
    """Strip emoji and stray formatting before handing text to the TTS
    engine.

    Some TTS voices (edge-tts included) speak an emoji's literal Unicode
    name ("smiling face with smiling eyes") instead of skipping it, and
    will read markdown/stage-direction characters aloud too. LLM-generated
    lines occasionally include these despite prompt instructions not to,
    so scrub them here rather than relying on the LLM alone.
    """
    cleaned = _EMOJI_PATTERN.sub("", text)
    # Parenthetical/bracketed asides the model sometimes slips into the
    # voiceover line itself, e.g. "(smiling)", "[pause]" — these are almost
    # never core sentence content, so drop them entirely.
    cleaned = re.sub(r"\([^)]*\)|\[[^\]]*\]", "", cleaned)
    # Markdown emphasis/heading/strikethrough markers — unlike the asides
    # above, `*word*`/`_word_` usually wrap real words the model meant to
    # say, just typographically emphasized, so strip only the marker
    # characters rather than deleting the text they wrap.
    cleaned = re.sub(r"[#*_~`]+", "", cleaned)
    return re.sub(r"\s{2,}", " ", cleaned).strip()


async def synthesize_scene_audio(
    scene: Scene,
    voice: VoiceConfig,
    output_dir: Path,
    language: str = "en",
) -> Path:
    """Generate the voiceover audio for a single scene and return its path.

    Extension follows the engine — Piper writes WAV, the others MP3 —
    since everything downstream (whisper, ffmpeg) reads either.
    """
    suffix = "wav" if voice.provider == TTSProvider.PIPER else "mp3"
    output_path = output_dir / f"scene_{scene.index:02d}.{suffix}"
    await synthesize_line(scene.audio.voiceover_line, voice, output_path, language)
    return output_path


async def synthesize_line(
    text: str,
    voice: VoiceConfig,
    output_path: Path,
    language: str = "en",
    length_scale: float | None = None,
) -> Path:
    """Speak one line to `output_path`.

    Split out of `synthesize_scene_audio` so the voice-preview endpoint
    goes through the same provider dispatch a real render does — a preview
    produced by a different code path is a preview that can lie.

    `length_scale` stretches or compresses the delivery: below 1 is faster,
    above 1 is slower. Only Piper honours it, and only dubbing asks for it,
    where a translated sentence has to land inside the slot the original
    occupied. Left unset everywhere else, which is the voice's natural pace.
    """
    cleaned = clean_text_for_tts(text)

    if voice.provider == TTSProvider.EDGE_TTS:
        await _synthesize_edge_tts(cleaned, voice, output_path)
    elif voice.provider == TTSProvider.PIPER:
        await _synthesize_piper(cleaned, voice, output_path, language, length_scale)
    elif voice.provider == TTSProvider.COQUI_XTTS:
        await _synthesize_xtts(cleaned, voice, output_path)
    else:
        raise ValueError(f"Unsupported TTS provider: {voice.provider}")

    return output_path


async def _synthesize_edge_tts(text: str, voice: VoiceConfig, output_path: Path) -> None:
    import edge_tts

    communicate = edge_tts.Communicate(
        text=text,
        voice=voice.voice_id,
        rate=voice.rate,
        pitch=voice.pitch,
    )
    await communicate.save(str(output_path))


# Default Piper voice per language. Every entry is a real medium-quality
# voice in rhasspy/piper-voices (MIT), verified present in that repo's
# voices.json. Piper covers 9 of the 10 languages ShortPulse offers —
# Japanese has no Piper voice, which _resolve_piper_voice reports clearly
# rather than failing deep inside synthesis.
# Repo layout is "<lang>/<locale>/<speaker>/<quality>/<name>" — the leading
# language directory is easy to miss and yields a 404 without it.
PIPER_VOICE_BY_LANGUAGE: dict[str, str] = {
    "en": "en/en_US/ryan/medium/en_US-ryan-medium",
    "tr": "tr/tr_TR/dfki/medium/tr_TR-dfki-medium",
    "es": "es/es_ES/davefx/medium/es_ES-davefx-medium",
    "fr": "fr/fr_FR/tom/medium/fr_FR-tom-medium",
    "de": "de/de_DE/thorsten/medium/de_DE-thorsten-medium",
    "pt": "pt/pt_BR/faber/medium/pt_BR-faber-medium",
    "ar": "ar/ar_JO/kareem/medium/ar_JO-kareem-medium",
    "ru": "ru/ru_RU/dmitri/medium/ru_RU-dmitri-medium",
    "it": "it/it_IT/paola/medium/it_IT-paola-medium",
}

_PIPER_REPO = "rhasspy/piper-voices"

# Loading a voice costs a few hundred ms and every scene reuses the same
# one, so keep them for the process lifetime (same reasoning as the
# faster-whisper cache above).
_piper_voice_cache: dict[str, object] = {}


def _resolve_piper_voice(voice: VoiceConfig, language: str) -> str:
    """Piper voice key for this request.

    `voice.voice_id` wins if it already looks like a Piper voice (a path or
    a bare voice name); otherwise fall back to the language default. This
    lets the same VoiceConfig.voice_id field carry an edge-tts name like
    "tr-TR-AhmetNeural" without it being mistaken for a Piper voice.
    """
    candidate = (voice.voice_id or "").strip()
    if candidate and ("/" in candidate or candidate.endswith(".onnx")):
        return candidate

    key = PIPER_VOICE_BY_LANGUAGE.get(language)
    if key is None:
        raise ValueError(
            f"Piper has no voice for language {language!r}. "
            f"Supported: {sorted(PIPER_VOICE_BY_LANGUAGE)}. "
            "Pick another TTS provider for this language."
        )
    return key


def _load_piper_voice(voice_key: str):
    """Load (downloading and caching on first use) a Piper ONNX voice."""
    if voice_key in _piper_voice_cache:
        return _piper_voice_cache[voice_key]

    from huggingface_hub import hf_hub_download
    from piper import PiperVoice

    if voice_key.endswith(".onnx") and Path(voice_key).exists():
        model_path, config_path = voice_key, f"{voice_key}.json"
    else:
        # Repo paths are "<locale>/<speaker>/<quality>/<name>"; the model and
        # its config sit side by side under that prefix.
        base = voice_key[: -len(".onnx")] if voice_key.endswith(".onnx") else voice_key
        logger.info("Downloading Piper voice %s", base)
        model_path = hf_hub_download(_PIPER_REPO, f"{base}.onnx")
        config_path = hf_hub_download(_PIPER_REPO, f"{base}.onnx.json")

    _piper_voice_cache[voice_key] = PiperVoice.load(model_path, config_path=config_path)
    return _piper_voice_cache[voice_key]


async def _synthesize_piper(
    text: str,
    voice: VoiceConfig,
    output_path: Path,
    language: str = "en",
    length_scale: float | None = None,
) -> None:
    """Fully local synthesis with a Piper ONNX voice (MIT licensed).

    Unlike edge-tts this runs entirely on the machine — no network call, no
    third-party terms to comply with — which is what makes it viable as the
    default for a hosted service.

    `VoiceConfig.rate` is deliberately not consulted here: it is an edge-tts
    string ("+10%") and Piper expresses the same idea as a multiplier on
    phoneme length. `length_scale` is that multiplier, passed explicitly by
    the one caller that needs it rather than inferred from a field shaped
    for a different engine.
    """
    import asyncio
    import wave

    voice_key = _resolve_piper_voice(voice, language)

    def _run() -> None:
        piper_voice = _load_piper_voice(voice_key)
        syn_config = None
        if length_scale is not None:
            from piper import SynthesisConfig

            syn_config = SynthesisConfig(length_scale=length_scale)
        # Piper emits WAV; the rest of the pipeline is format-agnostic since
        # ffmpeg reads whatever the scene clip step is handed.
        with wave.open(str(output_path), "wb") as wav:
            piper_voice.synthesize_wav(text, wav, syn_config=syn_config)

    await asyncio.to_thread(_run)


async def _synthesize_xtts(text: str, voice: VoiceConfig, output_path: Path) -> None:
    """Voice-cloning fallback using Coqui XTTS-v2. `voice.voice_id` is a
    path to a reference speaker .wav clip."""
    from TTS.api import TTS  # heavy import, deferred to keep API startup fast

    tts = TTS("tts_models/multilingual/multi-dataset/xtts_v2")
    tts.tts_to_file(
        text=text,
        speaker_wav=voice.voice_id,
        language="en",
        file_path=str(output_path),
    )


def _get_whisper_model(model_size: str, device: str, compute_type: str):
    cache_key = f"{model_size}:{device}:{compute_type}"
    if cache_key not in _whisper_model_cache:
        from faster_whisper import WhisperModel

        logger.info("Loading faster-whisper model %s on %s", model_size, device)
        _whisper_model_cache[cache_key] = WhisperModel(
            model_size, device=device, compute_type=compute_type
        )
    return _whisper_model_cache[cache_key]


def transcribe_segments(
    audio_path: Path,
    model_size: str = "small",
    device: str = "cpu",
    compute_type: str = "int8",
    language: str | None = None,
) -> list[Segment]:
    """Transcribe into sentences, each carrying its own words.

    `transcribe_word_timestamps` below flattens Whisper's segments away,
    which is right for captions — they are chunked by word count, not by
    sentence. Dubbing cannot use that: it translates a sentence at a time
    and has to put the replacement back in the slot the original occupied.
    So this keeps what the other one discards. Same model, same cache, one
    pass either way.

    Segments with no words are dropped rather than kept as empty slots:
    Whisper emits them for music and silence, and there is nothing to
    translate or re-speak in one.
    """
    model = _get_whisper_model(model_size, device, compute_type)
    segments, _info = model.transcribe(str(audio_path), word_timestamps=True, language=language)

    out: list[Segment] = []
    for segment in segments:
        words = [
            Word(
                text=word.word.strip(),
                start_ms=round(word.start * 1000),
                end_ms=round(word.end * 1000),
                confidence=getattr(word, "probability", None),
            )
            for word in segment.words or []
        ]
        if not words:
            continue
        out.append(
            Segment(
                text=segment.text.strip(),
                # Whisper's own segment bounds can sit a little outside the
                # first and last word; the words are what the caption track
                # is drawn from, so take the tighter pair and keep the two
                # consistent.
                start_ms=min(round(segment.start * 1000), words[0].start_ms),
                end_ms=max(round(segment.end * 1000), words[-1].end_ms),
                words=words,
            )
        )
    return out


def shift_segments(segments: list[Segment], offset_s: float) -> list[Segment]:
    """Move a transcript of a trimmed window back onto the original clock.

    A window transcription is timed from the window's own start, and
    everything downstream seeks into the **original** file — `cut_clip`
    takes `moment.start_s` and hands it straight to ffmpeg. Left
    unshifted, a moment found at 0:30 of a window that began at 20:00
    would cut the wrong half-minute of the video, silently, and only for
    the users who moved the slider.

    So the rule is: timings are absolute against the source from here on,
    and this is the one place that is true by construction. A zero offset
    returns the list untouched, which is the whole-source case.
    """
    if not offset_s:
        return segments

    offset_ms = round(offset_s * 1000)
    return [
        segment.model_copy(
            update={
                "start_ms": segment.start_ms + offset_ms,
                "end_ms": segment.end_ms + offset_ms,
                "words": [
                    word.model_copy(
                        update={
                            "start_ms": word.start_ms + offset_ms,
                            "end_ms": word.end_ms + offset_ms,
                        }
                    )
                    for word in segment.words
                ],
            }
        )
        for segment in segments
    ]


def transcribe_word_timestamps(
    audio_path: Path,
    model_size: str = "small",
    device: str = "cpu",
    compute_type: str = "int8",
    language: str | None = None,
) -> list[Word]:
    """Run faster-whisper on a rendered voiceover clip and return
    word-level timing. Runs synchronously (CPU/GPU-bound); call via
    asyncio.to_thread from async code paths.

    `language` is an ISO 639-1 code (matches ProjectConfig.language, e.g.
    "tr", "es") — passing it skips Whisper's own language-detection pass
    and avoids the rare case where a short clip gets misdetected.
    """
    model = _get_whisper_model(model_size, device, compute_type)
    segments, _info = model.transcribe(str(audio_path), word_timestamps=True, language=language)

    words: list[Word] = []
    for segment in segments:
        for word in segment.words or []:
            words.append(
                Word(
                    text=word.word.strip(),
                    start_ms=round(word.start * 1000),
                    end_ms=round(word.end * 1000),
                    confidence=getattr(word, "probability", None),
                )
            )
    return words


async def process_scene_audio(
    scene: Scene,
    voice: VoiceConfig,
    output_dir: Path,
    whisper_model_size: str = "small",
    whisper_device: str = "cpu",
    whisper_compute_type: str = "int8",
    language: str | None = None,
) -> Scene:
    """Full audio pipeline for one scene: synthesize -> transcribe -> attach
    timing data. Returns the scene with `audio.audio_path` and
    `audio.words` populated in place.
    """
    import asyncio

    audio_path = await synthesize_scene_audio(scene, voice, output_dir, language or "en")
    words = await asyncio.to_thread(
        transcribe_word_timestamps,
        audio_path,
        whisper_model_size,
        whisper_device,
        whisper_compute_type,
        language,
    )

    scene.audio.audio_path = str(audio_path)
    scene.audio.words = words
    # Note this is the end of the last transcribed *word*, not the length of
    # the audio file — Whisper puts that boundary at the final vowel, so it
    # runs short by 80-250ms. Good enough for a rough estimate, wrong as a
    # clip length: cutting a scene here clips the trailing consonant. The
    # renderer probes the file instead (render_engine._scene_duration_s) and
    # overwrites this with the real encoded duration once the clip exists.
    scene.audio.duration_ms = words[-1].end_ms if words else int(scene.duration_s * 1000)
    return scene
