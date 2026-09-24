"""Following the speaker, without a detector, a video or ffmpeg.

`reframe` is split so that the part worth testing is arithmetic. Finding
a face is OpenCV's job and is not re-tested here; deciding where the crop
should sit given a set of detections is this codebase's job, and it is
the half that decides whether the result is watchable.

The three properties that matter, in the order they bite:

  * a subject who does not move produces a crop that does not move,
  * a crop never leaves the frame, whatever the detections say,
  * a jump in the detections becomes a pan rather than a teleport.
"""

from __future__ import annotations

from app.services import reframe
from app.services.reframe import Sample

# 1080 wide out of a 3413-wide scaled frame — a 16:9 source becoming 9:16,
# which is the case this exists for.
CROP = 1080 / 3413


def _track(centres: list[float]) -> list[Sample]:
    return [Sample(time_s=i / reframe.SAMPLE_FPS, centre=c) for i, c in enumerate(centres)]


def _left_edges(path: list[Sample]) -> list[float]:
    return [round(p.centre, 4) for p in path]


# --- the still case, which is most of them ------------------------------


def test_a_motionless_subject_produces_a_motionless_crop():
    """The failure this guards against is a slow wander on a talking head
    that never moved — worse than the centre-crop it replaced, because at
    least that one held still."""
    path = reframe.crop_path(_track([0.5] * 20), duration_s=6.0, crop_fraction=CROP)

    assert len(set(_left_edges(path))) == 1


def test_jitter_inside_the_deadzone_does_not_move_the_crop():
    """Detections wobble by a pixel or two on a still head. Following that
    is what makes an auto-framed video look cheap."""
    wobble = [0.5 + (0.01 if i % 2 else -0.01) for i in range(20)]

    path = reframe.crop_path(_track(wobble), duration_s=6.0, crop_fraction=CROP)

    assert len(set(_left_edges(path))) == 1


# --- staying inside the picture -----------------------------------------


def test_the_crop_never_runs_off_either_edge():
    """A face detected at the very edge would otherwise ask for a crop
    that starts before the frame or ends after it — ffmpeg clamps, but it
    clamps to something nobody chose."""
    for centres in ([0.0] * 12, [1.0] * 12):
        path = reframe.crop_path(_track(centres), duration_s=4.0, crop_fraction=CROP)

        for sample in path:
            assert 0.0 <= sample.centre <= 1.0 - CROP + 1e-9


def test_a_crop_as_wide_as_the_source_has_nowhere_to_go():
    """A 9:16 source needs no reframing at all, and the arithmetic for
    where to put the crop degenerates — it must not divide by zero or
    wander off the edge."""
    path = reframe.crop_path(_track([0.2, 0.8, 0.5]), duration_s=1.0, crop_fraction=1.0)

    assert all(abs(sample.centre) < 1e-9 for sample in path)


# --- movement -----------------------------------------------------------


def test_a_cut_to_another_speaker_pans_rather_than_teleports():
    """One frame the subject is left, the next they are right. Snapping
    reads as a glitch; the limit turns it into a camera move."""
    path = reframe.crop_path(
        _track([0.2] * 6 + [0.8] * 6), duration_s=4.0, crop_fraction=CROP
    )

    steps = [abs(b.centre - a.centre) for a, b in zip(path, path[1:], strict=False)]
    # An absolute bound, not one derived from MAX_PAN_PER_S — a limit
    # computed from the constant it is checking moves when the constant
    # does, and passes however fast the pan is allowed to be. The jump
    # asked for here is 0.6 of the frame; a third of that in one step
    # would already look like a cut.
    assert max(steps) < 0.1
    # And it does eventually get there, or the limit would just be a way
    # of never following anyone.
    assert path[-1].centre > path[0].centre


def test_a_subject_who_walks_across_is_followed():
    drift = [0.2 + 0.03 * i for i in range(20)]

    path = reframe.crop_path(_track(drift), duration_s=6.0, crop_fraction=CROP)

    assert path[-1].centre > path[0].centre + 0.1


def test_nothing_detected_means_no_path_at_all():
    """Which the caller reads as "centre-crop". A video with no faces in
    it is a video with no subject to follow, and inventing one would be
    worse than the honest middle."""
    assert reframe.crop_path([], duration_s=6.0, crop_fraction=CROP) == []


# --- what ffmpeg is handed ----------------------------------------------


def test_the_script_addresses_the_crop_filter_by_name():
    """sendcmd targets a filter by name; a typo here is a file ffmpeg
    reads, accepts and ignores, leaving a centre-crop and no error."""
    script = reframe.sendcmd_script(_track([0.0, 0.25]), scaled_width=3413, crop_width=1080)

    for line in script.strip().splitlines():
        assert " crop x " in line
        assert line.endswith(";")


def test_the_script_never_asks_for_a_crop_past_the_frame():
    """x is a pixel offset into the scaled frame, so the largest legal
    value is the overhang — not the frame width."""
    script = reframe.sendcmd_script(_track([0.9, 1.0]), scaled_width=3413, crop_width=1080)

    for line in script.strip().splitlines():
        assert int(line.split()[-1].rstrip(";")) <= 3413 - 1080


def test_the_first_command_starts_at_zero():
    """A path that starts late leaves the opening frames on whatever the
    crop was initialised to — which is the left edge, not the subject."""
    script = reframe.sendcmd_script(_track([0.5, 0.5]), scaled_width=3413, crop_width=1080)

    assert script.startswith("0.000 ")
