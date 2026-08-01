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

from app.schemas.project import Scene, TTSProvider, VoiceConfig, Word

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
) -> Path:
    """Generate the voiceover .mp3 for a single scene and return its path."""
    output_path = output_dir / f"scene_{scene.index:02d}.mp3"
    text = clean_text_for_tts(scene.audio.voiceover_line)

    if voice.provider == TTSProvider.EDGE_TTS:
        await _synthesize_edge_tts(text, voice, output_path)
    elif voice.provider == TTSProvider.PIPER:
        await _synthesize_piper(text, voice, output_path)
    elif voice.provider == TTSProvider.COQUI_XTTS:
        await _synthesize_xtts(text, voice, output_path)
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


async def _synthesize_piper(text: str, voice: VoiceConfig, output_path: Path) -> None:
    """Offline fallback using a local Piper ONNX voice model.

    Requires the `piper-tts` CLI and a downloaded .onnx voice file at
    `voice.voice_id` (a filesystem path in this mode).
    """
    import asyncio

    proc = await asyncio.create_subprocess_exec(
        "piper",
        "--model",
        voice.voice_id,
        "--output_file",
        str(output_path),
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.PIPE,
    )
    _, stderr = await proc.communicate(input=text.encode("utf-8"))
    if proc.returncode != 0:
        raise RuntimeError(f"piper-tts failed: {stderr.decode(errors='ignore')}")


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

    audio_path = await synthesize_scene_audio(scene, voice, output_dir)
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
    scene.audio.duration_ms = words[-1].end_ms if words else int(scene.duration_s * 1000)
    return scene
