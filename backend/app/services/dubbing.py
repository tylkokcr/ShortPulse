"""Re-speak an uploaded video in another language.

The picture is never touched. What comes out of here is a single audio
track, exactly as long as the source video, with each translated sentence
sitting at the timestamp its original occupied. Swap that track in
(`render_engine.finalize_render(voice_track=...)`) and the result is a dub:
the speaker's mouth is doing what it always did, and the words are in a
different language.

Three things make that work, and all three already existed:

  * Whisper hands back sentences, not just words — `transcribe_segments`
    stops throwing the segment boundaries away.
  * Piper takes a `length_scale`, so a translation that runs long can be
    spoken faster rather than spilling into the next sentence.
  * ffmpeg's `adelay` places a clip at an absolute time, so nothing here
    accumulates drift the way a concatenated track would.

What this deliberately does not do is lip-sync. The lips will not match,
and for a dub that is a convention rather than a defect — it is the
*same-language* case, where a viewer expects their own language's mouth
shapes, that this module refuses to serve.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path

from app.engines import audio_engine, render_engine, script_engine
from app.schemas.project import LLMConfig, Segment, VoiceConfig

logger = logging.getLogger(__name__)


class DubbingError(RuntimeError):
    pass


# How far a spoken sentence may miss its slot before we re-speak it. Under
# a tenth of a second, nobody hears the difference and a second synthesis
# is not worth the seconds it costs.
_FIT_TOLERANCE_MS = 120

# Bounds on the speed correction. Piper's length_scale is a multiplier on
# phoneme duration: below 1 is faster. Outside roughly this range the voice
# stops sounding like a person reading and starts sounding like a tape at
# the wrong speed, which is worse than a sentence that runs slightly long.
_MIN_LENGTH_SCALE = 0.85
_MAX_LENGTH_SCALE = 1.25

# The track is built at the rate scene clips already use, so the mix stage
# never has to resample mid-graph.
_SAMPLE_RATE = 48_000

_TRANSLATE_SYSTEM = (
    "You translate subtitles for a video. You will be given numbered lines "
    "of speech in {source}. Translate each line into {target}.\n"
    "Rules:\n"
    "- Return one translation per input line, keeping the numbering.\n"
    "- Keep each translation close in spoken length to the original. It "
    "will be read aloud in the time the original took.\n"
    "- Translate meaning, not words. Natural spoken {target}, not a gloss.\n"
    "- Keep names, numbers and units as they are.\n"
    "- The lines come from automatic speech recognition and can contain "
    "mis-heard words: a word split in two, a material or a place spelled as "
    "it sounded. Use the surrounding lines to recover the word the speaker "
    "meant, and translate that.\n"
    "- Never add a number, percentage, name or claim that is not in the "
    "source. If a line is unclear, translate what is there.\n"
    "- Write every line entirely in {target}. Leave nothing in {source} or "
    "any third language except proper names.\n"
    "- No commentary, no notes, no markdown.\n"
    'Reply with JSON: {{"lines": [{{"i": 0, "text": "..."}}]}}'
)


async def translate_segments(
    segments: list[Segment],
    source_language: str,
    target_language: str,
    llm: LLMConfig,
    *,
    strict: bool = False,
) -> list[str]:
    """Translate every sentence in one call.

    One call rather than one per sentence, because a translator that can
    see the paragraph resolves the pronouns and the terminology that a
    translator shown a single line cannot. The numbering is what lets the
    answer be put back in order.

    Lines the model drops are asked for again, once, on their own. After
    that a dub keeps the source text for what is still missing — a wrong
    sentence spoken is a visible failure, not a silent gap — while a
    `strict` caller (captions) gets an error instead: captions in the
    wrong language look like a finished video and are not one.
    """
    if not segments:
        return []

    source = script_engine.LANGUAGE_NAMES.get(source_language, source_language)
    target = script_engine.LANGUAGE_NAMES.get(target_language, target_language)
    system = _TRANSLATE_SYSTEM.format(source=source, target=target)

    by_index = await _translate_lines(
        llm, system, {i: segment.text for i, segment in enumerate(segments)}
    )
    missing = [i for i in range(len(segments)) if i not in by_index]
    if missing:
        logger.warning(
            "Translation missing %d of %d lines; asking again for those",
            len(missing),
            len(segments),
        )
        by_index.update(
            await _translate_lines(llm, system, {i: segments[i].text for i in missing})
        )
        missing = [i for i in range(len(segments)) if i not in by_index]

    if len(missing) == len(segments):
        # Nothing came back at all — not a dropped line but a translator
        # that did not answer. Neither a dub nor captions can be made of
        # the source text alone.
        raise DubbingError(f"The translation into {target} came back empty.")
    if missing and strict:
        raise DubbingError(
            f"The captions could not be translated into {target} "
            f"({len(missing)} of {len(segments)} lines came back empty)."
        )
    if missing:
        logger.warning(
            "Translation still missing %d of %d lines; keeping the original for those",
            len(missing),
            len(segments),
        )
    return [by_index.get(i, segments[i].text) for i in range(len(segments))]


async def _translate_lines(llm: LLMConfig, system: str, lines: dict[int, str]) -> dict[int, str]:
    """One request for these numbered lines, read back by number.

    Indexed rather than zipped: a model that drops or reorders a line would
    otherwise shift every sentence after it onto the wrong slot, and a dub
    that is one sentence out of step is worse than one with a missing
    sentence.
    """
    numbered = "\n".join(f"{i}. {text}" for i, text in lines.items())
    try:
        parsed = await script_engine.complete_json(llm, system, f"Lines to translate:\n{numbered}")
    except Exception:  # noqa: BLE001 - a failed attempt is reported as missing lines
        logger.exception("Translation request failed")
        return {}

    entries = parsed.get("lines") if isinstance(parsed, dict) else None
    if not isinstance(entries, list):
        return {}
    out: dict[int, str] = {}
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        try:
            index = int(entry.get("i"))  # type: ignore[arg-type]
        except (TypeError, ValueError):
            continue
        text = str(entry.get("text") or "").strip()
        if index in lines and text:
            out[index] = text
    return out


async def _speak_into_slot(
    text: str,
    slot_ms: int,
    voice: VoiceConfig,
    language: str,
    output_path: Path,
    ffprobe_binary: str,
) -> int:
    """Speak one sentence, then once more if it badly misses its slot.

    Returns the duration actually produced. Overrunning is tolerated —
    sentences in real speech overlap slightly and the next slot has its own
    absolute start — but a sentence that runs seconds long would talk over
    the one after it, which is what the retry is for.
    """
    await audio_engine.synthesize_line(text, voice, output_path, language)
    spoken_ms = await render_engine.probe_duration_ms(output_path, ffprobe_binary)

    if slot_ms <= 0 or abs(spoken_ms - slot_ms) <= _FIT_TOLERANCE_MS or spoken_ms <= 0:
        return spoken_ms

    scale = max(_MIN_LENGTH_SCALE, min(_MAX_LENGTH_SCALE, slot_ms / spoken_ms))
    if abs(scale - 1.0) < 0.02:
        return spoken_ms

    await audio_engine.synthesize_line(
        text, voice, output_path, language, length_scale=scale
    )
    return await render_engine.probe_duration_ms(output_path, ffprobe_binary)


def _mix_args(clips: list[tuple[Path, int]], total_ms: int, output_path: Path) -> list[str]:
    """ffmpeg arguments that place each clip at its own timestamp.

    `adelay` is the whole trick: every clip is positioned against the start
    of the track rather than against the clip before it, so a sentence that
    came out long moves nothing except itself. A concatenated track would
    have pushed every later sentence out of sync with the picture.
    """
    total_s = total_ms / 1000

    if not clips:
        # A video whose speech Whisper could not segment still needs a
        # track of the right length, or the mux would fall back to the
        # original audio and the "dub" would silently be the source.
        return [
            "-f", "lavfi",
            "-i", f"anullsrc=r={_SAMPLE_RATE}:cl=mono",
            "-t", f"{total_s:.3f}",
            "-c:a", "pcm_s16le",
            str(output_path),
        ]

    args: list[str] = []
    for path, _ in clips:
        args += ["-i", str(path)]

    chains = []
    for index, (_, start_ms) in enumerate(clips):
        chains.append(
            f"[{index}:a]aresample={_SAMPLE_RATE},aformat=channel_layouts=mono,"
            f"adelay=delays={start_ms}:all=1[s{index}]"
        )
    labels = "".join(f"[s{i}]" for i in range(len(clips)))
    # normalize=0 for the same reason finalize_render gives: amix otherwise
    # divides every input by their count, and here that would quieten the
    # whole dub in proportion to how many sentences it has.
    chains.append(
        f"{labels}amix=inputs={len(clips)}:duration=longest:dropout_transition=0:normalize=0[mixed]"
    )
    # Pad to the source's length. The mix ends at the last word; the video
    # does not, and a track that stops short would let `-shortest` cut the
    # picture.
    chains.append(f"[mixed]apad=whole_dur={total_s:.3f}[aout]")

    args += [
        "-filter_complex", ";".join(chains),
        "-map", "[aout]",
        "-t", f"{total_s:.3f}",
        "-c:a", "pcm_s16le",
        str(output_path),
    ]
    return args


async def build_dub_track(
    segments: list[Segment],
    translations: list[str],
    voice: VoiceConfig,
    target_language: str,
    total_duration_ms: int,
    work_dir: Path,
    ffmpeg_binary: str = "ffmpeg",
    ffprobe_binary: str = "ffprobe",
) -> tuple[Path, list[Segment]]:
    """Speak the translations and lay them out against the original timing.

    Hands back the finished track and the segments retimed to what was
    actually spoken, so the caption burn can describe the new audio rather
    than the old.
    """
    if len(segments) != len(translations):
        raise DubbingError(
            f"{len(segments)} segments but {len(translations)} translations"
        )

    work_dir.mkdir(parents=True, exist_ok=True)

    clips: list[tuple[Path, int]] = []
    spoken: list[Segment] = []

    for index, (segment, text) in enumerate(zip(segments, translations, strict=True)):
        clip_path = work_dir / f"dub_{index:03d}.wav"
        spoken_ms = await _speak_into_slot(
            text,
            segment.duration_ms,
            voice,
            target_language,
            clip_path,
            ffprobe_binary,
        )
        if spoken_ms <= 0:
            logger.warning("Segment %d produced no audio; skipping", index)
            continue
        clips.append((clip_path, segment.start_ms))
        spoken.append(
            Segment(
                text=text,
                start_ms=segment.start_ms,
                end_ms=segment.start_ms + spoken_ms,
                words=[],
            )
        )

    track_path = work_dir / "dub.wav"
    await render_engine.run_ffmpeg(
        _mix_args(clips, total_duration_ms, track_path), ffmpeg_binary
    )
    return track_path, spoken


def words_from_segments(segments: list[Segment]) -> list:
    """Spread each sentence's words evenly across the time it is spoken.

    The translated audio has no transcript of its own — running Whisper
    over our own synthesis to caption our own text would be a second pass
    to recover something we already know. Even spacing is not word-accurate
    timing, and it is not pretending to be: what it gets right is that the
    line on screen is the line being spoken, which is the part a viewer
    checks.
    """
    from app.schemas.project import Word

    words: list[Word] = []
    for segment in segments:
        tokens = segment.text.split()
        if not tokens:
            continue
        span = max(segment.duration_ms, 1)
        per = span / len(tokens)
        for position, token in enumerate(tokens):
            start = segment.start_ms + round(position * per)
            words.append(
                Word(
                    text=token,
                    start_ms=start,
                    end_ms=start + round(per),
                )
            )
    return words


# Languages written without spaces between words. A translated line in one
# of these comes back as a single "word" to str.split(), which would put a
# whole sentence on screen at once; it is cut into short runs instead, and
# subtitle_engine joins them without spaces.
UNSPACED_LANGUAGES = frozenset({"ja", "zh"})

# Characters per run for an unspaced language. Short, because a run is
# what one caption word is, and four of them make a line: at the caption
# size a 1080-wide frame holds about twelve CJK characters.
_UNSPACED_RUN = 3

_CJK_BREAKS = re.compile(r"(?<=[、。！？，．・「」『』])")


def _caption_tokens(text: str, language: str) -> list[str]:
    if language.split("-")[0].lower() not in UNSPACED_LANGUAGES:
        return text.split()
    tokens: list[str] = []
    for phrase in _CJK_BREAKS.split(text.replace(" ", "")):
        for start in range(0, len(phrase), _UNSPACED_RUN):
            run = phrase[start : start + _UNSPACED_RUN]
            if run:
                tokens.append(run)
    return tokens


def translated_caption_words(
    segments: list[Segment], translations: list[str], language: str
) -> list:
    """Caption words for a translation laid over the original speech.

    The voice is untouched, so each translated sentence has to occupy the
    time its original was spoken in — the line on screen is the line being
    said, which is what a viewer checks. Within the sentence the words are
    spread by length rather than evenly: a long word takes longer to read,
    and even spacing left short words up as long as long ones.

    The highlight then moves through the sentence at the speaker's pace.
    It cannot follow the speaker word for word — the words are not the
    ones being spoken — and it is not presented as if it did.
    """
    from app.schemas.project import Word

    words: list[Word] = []
    for segment, text in zip(segments, translations, strict=False):
        tokens = _caption_tokens(text, language)
        if not tokens:
            continue
        span = max(segment.end_ms - segment.start_ms, 1)
        weights = [max(len(token), 1) for token in tokens]
        total = sum(weights)
        cursor = float(segment.start_ms)
        for token, weight in zip(tokens, weights, strict=True):
            length = span * weight / total
            words.append(
                Word(
                    text=token,
                    start_ms=round(cursor),
                    end_ms=round(cursor + length),
                )
            )
            cursor += length
    return words
