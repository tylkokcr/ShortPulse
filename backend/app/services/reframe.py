"""Follow the speaker when a landscape recording becomes a vertical clip.

`cut_clip` has always centre-cropped, and said so in its own docstring:
a speaker sitting off to one side gets cropped off-centre, and fixing it
properly means finding them frame by frame. This is that.

What it does *not* do is touch the picture itself. It answers one
question — where is the subject, over time — and returns the answer as a
list of crop positions. `render_engine` turns those into an ffmpeg
`sendcmd` script and the existing crop filter does the work. Keeping the
two apart is what makes this testable without ffmpeg, a video file or a
GPU, exactly as `clipping` is testable without a model.

Three things matter more than the detector:

  * **Stillness.** Raw per-frame detections jitter by a few pixels even
    on a motionless head, and a crop that follows them is unwatchable in
    a way that centre-cropping never was. So the path is smoothed, and
    then only moved at all once the subject has drifted past a deadzone —
    a talking head that stays put produces a completely static crop.
  * **Gaps.** A face is missed whenever someone turns away, and a crop
    that snaps to centre for those frames and back afterwards is worse
    than one that never moved. A gap holds the last known position.
  * **Speed.** Detection runs on frames sampled a few times a second and
    scaled down small, because the subject does not move meaningfully
    between two frames 300ms apart and a 60-second clip should cost
    seconds, not minutes.

OpenCV is installed by the container (requirements-vision.txt) but the
import still lives inside the function that needs it, the same way every
torch import here does — a self-hosted install that skipped the extra
should run, not crash on startup. Absent, `is_available()` is False and the caller
centre-crops exactly as it did before — and logs that it is doing so,
because the difference between a tracked crop and a centred one does not
announce itself in the output.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)

# The bundled YuNet detector. 233KB, MIT, vendored rather than downloaded
# so a self-hosted install works offline and a first render is not also a
# first download.
MODEL_PATH = Path(__file__).resolve().parents[1] / "assets" / "models" / "face_detection_yunet.onnx"

# Frames per second to look at. Three is well past what a talking head
# needs — the smoothing below works in seconds, not frames — and it keeps
# a minute of video to under two hundred detections.
SAMPLE_FPS = 3.0

# Width the frames are scaled to before detection. Small on purpose:
# YuNet finds a head that occupies a useful part of a 360px frame, and
# anything smaller than that in the source is not the subject.
DETECT_WIDTH = 360

# How sure the detector has to be. Low enough to keep a profile view,
# high enough to ignore a face in a poster on the wall behind.
MIN_CONFIDENCE = 0.6

# Seconds of detections averaged together. Long enough to absorb a head
# turn, short enough to follow someone who actually walks across frame.
SMOOTHING_WINDOW_S = 1.2

# How far the subject may drift, as a fraction of the crop width, before
# the crop moves at all. This is what makes a still speaker produce a
# still frame instead of a slow wander.
DEADZONE = 0.12

# Maximum pan, as a fraction of the crop width per second. A cut to a
# different speaker is a jump in the detections; without this the crop
# teleports, which reads as a glitch rather than a camera move.
MAX_PAN_PER_S = 0.35


@dataclass(frozen=True)
class Sample:
    """Where the subject was, at one moment.

    `centre` is a fraction of the source width rather than a pixel, so the
    track survives the scaling that happens before the crop and can be
    reasoned about without knowing the output size.
    """

    time_s: float
    centre: float


def is_available() -> bool:
    """Whether this install can track a subject at all."""
    if not MODEL_PATH.exists():
        return False
    try:
        import cv2  # noqa: F401
    except ImportError:
        return False
    return True


async def track_subject(
    source: Path,
    start_s: float,
    duration_s: float,
    source_width: int,
    source_height: int,
    ffmpeg_binary: str = "ffmpeg",
) -> list[Sample]:
    """Where the subject is, through one stretch of a video.

    Returns an empty list when nothing was found at all, which the caller
    reads as "centre-crop" — a video of a landscape has no subject to
    follow and inventing one would be worse than the honest middle.
    """
    try:
        import cv2
        import numpy as np
    except ImportError:
        return []

    if source_width <= 0 or source_height <= 0:
        return []

    # Both dimensions stated, never `-1`. Asked to pick the height itself
    # ffmpeg is free to return an odd number, and the frame size then has
    # to be guessed back out of the byte count — which is ambiguous, since
    # several heights divide it exactly. Stating it makes the reshape
    # below arithmetic rather than inference.
    width = DETECT_WIDTH
    height = max(2, round(source_height * width / source_width / 2) * 2)

    # Sampled, scaled and piped rather than written out: a temp directory
    # of JPEGs for a 60-second clip is a few hundred files, and the only
    # thing they would buy is the ability to look at them.
    process = await asyncio.create_subprocess_exec(
        ffmpeg_binary,
        "-nostdin",
        "-ss", f"{start_s:.3f}",
        "-i", str(source),
        "-t", f"{duration_s:.3f}",
        "-vf", f"fps={SAMPLE_FPS},scale={width}:{height}",
        "-f", "rawvideo",
        "-pix_fmt", "bgr24",
        "-",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.DEVNULL,
    )
    raw, _ = await process.communicate()
    if process.returncode != 0 or not raw:
        logger.warning("Could not sample %s for subject tracking", source.name)
        return []

    frame_height = height
    stride = width * frame_height * 3
    if len(raw) % stride:
        logger.warning("Sampled frames from %s were not a whole number of frames", source.name)
        return []

    detector = cv2.FaceDetectorYN.create(
        str(MODEL_PATH), "", (width, frame_height), MIN_CONFIDENCE, 0.3, 5000
    )

    samples: list[Sample] = []
    for index in range(len(raw) // stride):
        frame = np.frombuffer(raw[index * stride : (index + 1) * stride], dtype=np.uint8)
        frame = frame.reshape((frame_height, width, 3))
        centre = _subject_centre(detector, frame, width)
        if centre is not None:
            samples.append(Sample(time_s=index / SAMPLE_FPS, centre=centre))

    return samples


def _subject_centre(detector, frame, width: int) -> float | None:
    """The one face worth following, as a fraction of the width.

    The largest, not the most confident: in an interview the person
    nearest the camera is the one the vertical crop is about, and
    confidence tracks image quality rather than importance. Two faces of
    a similar size are framed between them, because cutting one of them
    out of a two-shot is worse than centring on neither.
    """
    detector.setInputSize((width, frame.shape[0]))
    _, faces = detector.detect(frame)
    if faces is None or len(faces) == 0:
        return None

    boxes = [(float(f[0]), float(f[2])) for f in faces]  # x, w
    widest = max(w for _, w in boxes)
    # Everything within a quarter of the biggest face's width counts as
    # "the same size" — an interview shot from one camera never gives two
    # people identical head sizes.
    main = [(x, w) for x, w in boxes if w >= widest * 0.75]
    centres = [(x + w / 2) / width for x, w in main]
    return sum(centres) / len(centres)


def crop_path(
    samples: list[Sample],
    duration_s: float,
    crop_fraction: float,
) -> list[Sample]:
    """The samples, turned into somewhere the crop can actually sit.

    `crop_fraction` is how much of the source width the crop keeps — the
    deadzone and the pan limit are both expressed against it, because a
    drift that is nothing in a wide crop is half the frame in a narrow
    one.

    The output is the *left edge* of the crop as a fraction of the source
    width, already clamped to the frame, and sampled at the same rate as
    the input. An empty input gives an empty path, which the caller reads
    as centre-crop.
    """
    if not samples:
        return []

    smoothed = _smooth(samples)
    half = crop_fraction / 2
    deadzone = crop_fraction * DEADZONE
    max_step = crop_fraction * MAX_PAN_PER_S / SAMPLE_FPS

    path: list[Sample] = []
    # Start where the subject already is rather than panning in from the
    # middle: the first frame is the one most likely to be a thumbnail.
    current = _clamp(smoothed[0].centre, half, 1 - half)

    for sample in smoothed:
        wanted = _clamp(sample.centre, half, 1 - half)
        drift = wanted - current
        if abs(drift) > deadzone:
            # Move only the distance past the deadzone, so the crop
            # settles at the edge of it rather than centring exactly and
            # then immediately needing to move back.
            target = wanted - deadzone if drift > 0 else wanted + deadzone
            step = _clamp(target - current, -max_step, max_step)
            current = _clamp(current + step, half, 1 - half)
        path.append(Sample(time_s=sample.time_s, centre=current - half))

    return path


def _smooth(samples: list[Sample]) -> list[Sample]:
    """A moving average, over time rather than over samples.

    Over time because the samples are not evenly spaced: a frame with no
    face in it is missing entirely, and averaging "the last five samples"
    would silently widen the window across a gap to something that spans
    several seconds.
    """
    window = SMOOTHING_WINDOW_S / 2
    out: list[Sample] = []
    for sample in samples:
        nearby = [
            other.centre
            for other in samples
            if abs(other.time_s - sample.time_s) <= window
        ]
        out.append(Sample(time_s=sample.time_s, centre=sum(nearby) / len(nearby)))
    return out


def _clamp(value: float, low: float, high: float) -> float:
    if low > high:
        # A crop as wide as the source: there is nowhere to move it to.
        return (low + high) / 2
    return max(low, min(high, value))


def sendcmd_script(path: list[Sample], scaled_width: int, crop_width: int) -> str:
    """The crop path, as commands ffmpeg's `sendcmd` filter understands.

    One line per sample, addressing the `crop` filter's `x` by name. This
    rather than a `crop=x=<expression>`: an expression covering a minute
    of video is hundreds of nested `if(between(t,...))` calls, which
    ffmpeg will parse and nobody will ever debug.
    """
    lines = []
    travel = max(scaled_width - crop_width, 0)
    for sample in path:
        # The path is a fraction of the *source* width, and the crop
        # happens after the scale — but both scale by the same factor, so
        # the fraction carries across untouched.
        x = int(round(_clamp(sample.centre, 0, 1) * scaled_width))
        lines.append(f"{sample.time_s:.3f} crop x {min(x, travel)};")
    return "\n".join(lines) + "\n"
