"""Puppet shots for a story series: the same drawn people in every shot.

Drawing every shot afresh — even from reference sheets, even checked and
redrawn — let faces drift: a husband turned into an old man in a hat, a
bald baby, a man in glasses he does not wear. The serialised stories this
format is modelled on do not redraw their people either: each character is
drawn once in a few poses and placed into the rooms.

So, per cast member and once per series:

- a half-length portrait, facing the viewer, mouth closed (FLUX, in the
  series' style);
- the same portrait with only the face changed — talking, blinking,
  worried, scared, happy (Kontext Pro) — each aligned back onto the
  portrait and merged on the face alone, so nothing else in the drawing
  moves between poses;
- the portrait cut out (a background remover), one alpha for every pose.

And per shot, by code: the room's plate, the people in it, the speaker's
mouth opening with the loudness of their own line, the expression the
line's tone asks for, a blink every few seconds, a breath, a slow push in.
"""

from __future__ import annotations

import asyncio
import base64
import logging
import math
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

BACKGROUND_REMOVER = (
    "851-labs/background-remover:a029dff38972b5fda4ec5d75d7d1cd25aeff621d2cf4946a41055d7db66b80bc"
)
EDIT_MODEL = "black-forest-labs/flux-kontext-pro"

# The face changes a pose set has, and the edit that makes each.
_KEEP = (
    " Change nothing else at all: same head position, same angle, same framing, same hair, "
    "same clothes, same colours, same background."
)
POSE_EDITS = {
    "talk": "Open the mouth slightly, as if speaking mid-word." + _KEEP,
    "blink": "Close both eyes, as in a blink." + _KEEP,
    "worried": "Make the expression worried: eyebrows raised together, lips pressed." + _KEEP,
    "scared": "Make the expression frightened: eyes wide, eyebrows up, mouth slightly open." + _KEEP,
    "happy": "Make the expression a warm, small smile." + _KEEP,
}
POSES = ("neutral", *POSE_EDITS)

# A line's tone tags (script_engine.TONES) as the face that shows them.
_TONE_FACE = {
    "tense": "worried", "nervous": "worried", "sad": "worried", "crying": "worried",
    "sighs": "worried", "tired": "worried", "angry": "worried", "firm": "worried",
    "scared": "scared", "shocked": "scared", "surprised": "scared", "whispers": "scared",
    "shouting": "scared",
    "laughs": "happy", "excited": "happy", "sarcastic": "happy", "curious": "neutral",
    "softly": "neutral",
}


def face_for(tone: str | None) -> str:
    for tag in (tone or "").split(","):
        face = _TONE_FACE.get(tag.strip())
        if face:
            return face
    return "neutral"


@dataclass
class Puppet:
    """A drawn person: their poses (BGR, all one size) and one alpha."""

    poses: dict[str, Any]
    alpha: Any


def _imread(*args: Any) -> Any:
    """cv2.imread, typed loosely: its stubs make every use an Optional."""
    import cv2

    return cv2.imread(*args)


def puppet_dir(root: Path, name: str) -> Path:
    import re

    slug = re.sub(r"[^a-z0-9]+", "-", name.casefold()).strip("-") or "member"
    return root / "series" / "puppets" / slug


def _uri(path: Path) -> str:
    return "data:image/png;base64," + base64.b64encode(path.read_bytes()).decode()


async def draw_puppet(look: str, folder: Path, settings, style) -> Path:
    """Draw a person's pose set into `folder` (portrait, poses, alpha)."""
    from app.engines.visual_engine import (
        _download,
        _replicate_image_input,
        _replicate_output_url,
        _replicate_predict,
    )
    from app.schemas.project import Scene, SceneAudio, SceneVisual

    folder.mkdir(parents=True, exist_ok=True)
    base = folder / "neutral.png"
    portrait = Scene(
        index=0,
        duration_s=3,
        visual=SceneVisual(
            prompt=(
                f"half-length portrait of {look}, facing the viewer, shoulders and arms relaxed, "
                "calm neutral expression with the mouth closed and eyes open, centred, "
                "plain flat light grey background, nothing else in the picture"
            )
        ),
        audio=SceneAudio(voiceover_line=""),
    )
    image_input = _replicate_image_input(portrait, style, None, settings)
    image_input["aspect_ratio"] = "3:4"
    prediction = await _replicate_predict(
        {"version": settings.replicate_image_model, "input": image_input}, settings
    )
    await _download(_replicate_output_url(prediction), base)

    async def edit(pose: str, instruction: str) -> None:
        made = await _replicate_predict(
            {
                "version": EDIT_MODEL,
                "input": {
                    "input_image": _uri(base),
                    "prompt": instruction,
                    "aspect_ratio": "match_input_image",
                    "output_format": "png",
                },
            },
            settings,
        )
        await _download(_replicate_output_url(made), folder / f"{pose}_raw.png")

    async def cut() -> None:
        made = await _replicate_predict(
            {"version": BACKGROUND_REMOVER, "input": {"image": _uri(base), "format": "png"}},
            settings,
        )
        await _download(_replicate_output_url(made), folder / "cutout.png")

    await asyncio.gather(*(edit(p, i) for p, i in POSE_EDITS.items()), cut())
    await asyncio.to_thread(_merge_poses, folder)
    (folder / "look.txt").write_text(look, encoding="utf-8")
    return folder


def _merge_poses(folder: Path) -> None:
    """Align each edited pose onto the portrait and keep only its face:
    an edit also nudges hair, collar and framing, and in a cut between two
    poses that reads as the person twitching."""
    import cv2
    import numpy as np

    base = _imread(str(folder / "neutral.png"))
    height, width = base.shape[:2]
    for pose in POSE_EDITS:
        raw = folder / f"{pose}_raw.png"
        if not raw.is_file():
            continue
        variant = cv2.resize(_imread(str(raw)), (width, height))
        g1 = cv2.cvtColor(base, cv2.COLOR_BGR2GRAY).astype(np.float32)
        g2 = cv2.cvtColor(variant, cv2.COLOR_BGR2GRAY).astype(np.float32)
        scale = 0.25
        small1 = cv2.resize(g1, None, fx=scale, fy=scale)
        small2 = cv2.resize(g2, None, fx=scale, fy=scale)
        warp: Any = np.eye(2, 3, dtype=np.float32)
        ecc: Any = cv2.findTransformECC
        try:
            criteria = (cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 200, 1e-6)
            _, warp = ecc(small1, small2, warp, cv2.MOTION_AFFINE, criteria, None, 5)
        except cv2.error:
            logger.warning("Could not align pose %s in %s", pose, folder.name)
        warp[:, 2] /= scale
        variant = cv2.warpAffine(
            variant, warp, (width, height),
            flags=cv2.INTER_LINEAR | cv2.WARP_INVERSE_MAP, borderMode=cv2.BORDER_REPLICATE,
        )
        diff = cv2.absdiff(
            cv2.GaussianBlur(variant, (0, 0), 2), cv2.GaussianBlur(base, (0, 0), 2)
        ).max(axis=2)
        mask: Any = (diff > 28).astype(np.uint8) * 255
        mask[int(height * 0.45):] = 0  # the face is in the top of a half-length portrait
        mask = cv2.dilate(mask, np.ones((25, 25), np.uint8))
        soft = cv2.GaussianBlur(mask, (0, 0), 9).astype(np.float32)[..., None] / 255.0
        merged = (base * (1 - soft) + variant * soft).astype(np.uint8)
        cv2.imwrite(str(folder / f"{pose}.png"), merged)


def load_puppet(folder: Path) -> Puppet | None:
    import cv2

    base = _imread(str(folder / "neutral.png"))
    cut = _imread(str(folder / "cutout.png"), cv2.IMREAD_UNCHANGED)
    if base is None or cut is None or cut.ndim != 3 or cut.shape[2] != 4:
        return None
    height, width = base.shape[:2]
    alpha = cv2.resize(cut[..., 3], (width, height)).astype("float32") / 255.0
    poses = {"neutral": base}
    for pose in POSE_EDITS:
        image = _imread(str(folder / f"{pose}.png"))
        poses[pose] = image if image is not None else base
    return Puppet(poses=poses, alpha=alpha)


def _loudness(audio: Path | None, fps: int, frames: int, ffmpeg: str) -> list[float]:
    """Per-frame loudness of a line, 0 where there is none."""
    import numpy as np

    if audio is None or not audio.is_file():
        return [0.0] * frames
    raw = subprocess.run(
        [ffmpeg, "-v", "error", "-i", str(audio), "-f", "f32le", "-ac", "1", "-ar", "16000", "-"],
        capture_output=True, check=False,
    ).stdout
    samples = np.frombuffer(raw, np.float32)
    step = 16000 / fps
    out = []
    for k in range(frames):
        chunk = samples[int(k * step): int((k + 1) * step)]
        out.append(float(np.sqrt((chunk**2).mean())) if chunk.size else 0.0)
    return out


def plan_framing(shots: list[tuple[list[str], str | None, str | None]]) -> list[str]:
    """A shot size for each shot, from (people in frame, speaker, place).

    Every shot at one size is what made the first puppet episode read as a
    slideshow: the cut changed the picture and nothing else. So, as an edit
    is cut: a wide shot whenever the story arrives somewhere, a close one on
    most spoken lines, waist-up for the rest — and never the same size three
    times running, so a run of lines still cuts in and out."""
    out: list[str] = []
    previous_place: str | None = None
    for k, (people, speaker, place) in enumerate(shots):
        talking = bool(speaker) and speaker != "narrator" and speaker in people
        if not people:
            size = "wide"
        elif place != previous_place and k > 0:
            size = "wide"
        elif talking:
            size = "close" if (k % 3) != 2 else "medium"
        elif len(people) == 2:
            size = "medium"
        else:
            size = "medium" if k % 2 else "wide"
        if len(out) >= 2 and out[-1] == out[-2] == size and people:
            size = "medium" if size != "medium" else ("close" if talking else "wide")
        out.append(size)
        previous_place = place
    return out


def render_shot(
    output: Path,
    plate: Path | None,
    cast: list[tuple[str, Puppet]],
    speaker: str | None,
    tone: str | None,
    audio: Path | None,
    seconds: float,
    width: int,
    height: int,
    fps: int,
    ffmpeg: str = "ffmpeg",
    seed: int = 0,
    framing: str = "medium",
) -> Path:
    """One shot as a silent MP4: the room, its people, the speaker talking.

    `framing` is the shot size (see plan_framing): "close" is the speaker's
    face filling the frame over the room out of focus, "medium" the people
    from the waist up, "wide" the whole room with them small in it."""
    import cv2
    import numpy as np

    frames = max(1, round(seconds * fps))
    if plate is not None and plate.is_file():
        room = cv2.resize(_imread(str(plate)), (width, height))
    else:
        room = np.full((height, width, 3), 40, np.uint8)
    room_f = room.astype(np.float32)
    loud = _loudness(audio, fps, frames, ffmpeg)
    threshold = max(0.02, max(loud, default=0) * 0.18)
    face = face_for(tone)
    blink_every = 2.6 + (seed % 5) * 0.3

    side = -1 if seed % 2 else 1
    if framing == "close" and cast:
        # One face, big: whoever speaks, or the first person in frame. The
        # room behind goes soft, as behind a face shot on a long lens.
        cast = [next((c for c in cast if c[0] == speaker), cast[0])]
        room_f = cv2.GaussianBlur(room_f, (0, 0), sigmaX=width / 90)
        slots = [(0.5 + side * 0.03, 1.3)]
    elif framing == "wide":
        slots = [(0.5 + side * 0.12, 0.44)] if len(cast) == 1 else [(0.32, 0.38), (0.68, 0.38)]
    elif len(cast) == 1:
        # Where each person stands: one centred a little to a side, two apart.
        slots = [(0.5 + side * 0.06, 0.66)]
    else:
        slots = [(0.3, 0.52), (0.7, 0.52)]
    placed = []
    for (name, puppet), (cx, size) in zip(cast[:2], slots, strict=False):
        ph, pw = puppet.poses["neutral"].shape[:2]
        h = int(height * size)
        w = int(pw * h / ph)
        if framing == "close":
            # The head (the top fifth of a half-length portrait) just
            # above the middle; the shoulders run off the bottom.
            y0 = int(height * 0.4 - h * 0.2)
        else:
            y0 = height - h + int(height * 0.04)
        placed.append((name, puppet, int(width * cx - w / 2), y0, w, h))
    focus = next((p for p in placed if p[0] == speaker), placed[0] if placed else None)
    fx = (focus[2] + focus[4] / 2) if focus else width / 2
    fy = (focus[3] + focus[5] * 0.25) if focus else height / 2
    # A close shot barely moves; a wide one drifts in a little more.
    push = {"close": 0.035, "wide": 0.05}.get(framing, 0.07)

    proc = subprocess.Popen(
        [ffmpeg, "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "bgr24",
         "-s", f"{width}x{height}", "-r", str(fps), "-i", "-",
         "-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p", str(output)],
        stdin=subprocess.PIPE,
    )
    assert proc.stdin is not None
    try:
        for k in range(frames):
            t = k / fps
            frame = room_f.copy()
            for name, puppet, x0, y0, w, h in placed:
                speaking = name == speaker and loud[k] > threshold and (k // 3) % 2 == 0
                if (t + seed * 0.37) % blink_every < 0.13:
                    pose = "blink"
                elif speaking:
                    pose = "talk"
                else:
                    pose = face
                image = cv2.resize(puppet.poses[pose], (w, h)).astype(np.float32)
                alpha = cv2.resize(puppet.alpha, (w, h))[..., None]
                bob = int(2 * math.sin(t * 2 * math.pi * 0.3 + seed))
                ya, yb = max(y0 + bob, 0), min(y0 + bob + h, height)
                xa, xb = max(x0, 0), min(x0 + w, width)
                if ya >= yb or xa >= xb:
                    continue
                sy, sx = ya - (y0 + bob), xa - x0
                part_a = alpha[sy: sy + (yb - ya), sx: sx + (xb - xa)]
                part_i = image[sy: sy + (yb - ya), sx: sx + (xb - xa)]
                frame[ya:yb, xa:xb] = frame[ya:yb, xa:xb] * (1 - part_a) + part_i * part_a
            zoom = 1 + push * (k / max(frames - 1, 1))
            move = cv2.getRotationMatrix2D((fx, fy), 0, zoom)
            out = cv2.warpAffine(frame.astype(np.uint8), move, (width, height),
                                 borderMode=cv2.BORDER_REFLECT)
            proc.stdin.write(out.tobytes())
    finally:
        proc.stdin.close()
    if proc.wait() != 0:
        raise RuntimeError(f"ffmpeg could not encode puppet shot {output.name}")
    return output
