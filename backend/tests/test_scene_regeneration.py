"""Re-drawing one scene without disturbing the other nine.

The failure this exists to prevent is not a crash. It is a video that
still plays, and is subtly wrong — a timeline that shifted under its
captions, a stream-copy concat of clips that no longer match, a caption
track quietly replaced by the transcript the user had already corrected.
Each of those passes a smoke test and fails a viewer.

Nothing here touches Replicate, ffmpeg or Postgres: the engines are
stubbed, so what is under test is the orchestration.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.core.config import get_settings
from app.schemas.project import (
    CaptionTrack,
    EditSpec,
    Project,
    ProjectConfig,
    ProjectStatus,
    Scene,
    SceneAudio,
    SceneVisual,
    ScriptOutput,
    SubtitleStyle,
    VisualMode,
    Word,
)
from app.services import regeneration
from app.services.regeneration import NotRegenerable


def _scene(index: int, duration_ms: int = 4000) -> Scene:
    return Scene(
        index=index,
        duration_s=4.0,
        visual=SceneVisual(prompt=f"scene {index}", mode=VisualMode.FAST_HYBRID),
        audio=SceneAudio(
            voiceover_line=f"line {index}",
            duration_ms=duration_ms,
            words=[Word(text=f"w{index}", start_ms=0, end_ms=500)],
        ),
    )


def _project(scene_count: int = 3, mode: VisualMode = VisualMode.FAST_HYBRID) -> Project:
    return Project(
        config=ProjectConfig(topic="quiet people", visual_mode=mode),
        status=ProjectStatus.COMPLETE,
        script=ScriptOutput(
            topic="quiet people",
            hook="h",
            call_to_action="c",
            scenes=[_scene(i) for i in range(scene_count)],
            total_duration_s=4.0 * scene_count,
        ),
    )


@pytest.fixture
def finished(tmp_path, monkeypatch):
    """A project with everything a re-roll needs still on disk."""
    project = _project()
    paths = tmp_path / project.config.id
    for sub in ("audio", "output", "visuals", "subtitles"):
        (paths / sub).mkdir(parents=True)
    for i in range(3):
        (paths / "audio" / f"scene_{i:02d}.wav").write_bytes(b"a")
        (paths / "output" / f"clip_{i:02d}.mp4").write_bytes(f"clip {i}".encode())
    (paths / "output" / "final.mp4").write_bytes(b"final")
    (paths / "output" / "concatenated.mp4").write_bytes(b"old concat")

    monkeypatch.setattr(regeneration, "project_dir", lambda _id: paths)
    return project, paths


class _Engines:
    """Stands in for the image generator, the encoder and the concat.

    Records what it was asked for, because most of what matters here is
    *which* scene got re-encoded and which clips went into the concat.
    """

    def __init__(self, new_duration_ms: int | None = None):
        self.generated: list[tuple[int, int]] = []   # (scene index, variant)
        self.encoded: list[int] = []
        self.concatenated: list[list[str]] = []
        self.new_duration_ms = new_duration_ms

    def install(self, monkeypatch, paths: Path):
        async def generate(scene, mode, output_dir, settings, **kwargs):
            self.generated.append((scene.index, kwargs.get("variant", 0)))
            output_dir.mkdir(parents=True, exist_ok=True)
            asset = output_dir / f"scene_{scene.index:02d}.png"
            asset.write_bytes(b"png")
            scene.visual.asset_path = str(asset)
            return scene

        async def render_clip(scene, target, output_dir, **kwargs):
            self.encoded.append(scene.index)
            output_dir.mkdir(parents=True, exist_ok=True)
            out = output_dir / f"clip_{scene.index:02d}.mp4"
            out.write_bytes(b"new clip")
            if self.new_duration_ms is not None:
                scene.audio.duration_ms = self.new_duration_ms
            return out

        async def concat(clip_paths, output_dir, ffmpeg_binary="ffmpeg"):
            self.concatenated.append([p.name for p in clip_paths])
            out = output_dir / "concatenated.mp4"
            out.write_bytes(b"new concat")
            return out

        async def probe(path, ffprobe_binary="ffprobe"):
            return (1080, 1920)

        async def apply_edit(project, edit, settings):
            return paths / "output" / "final.mp4"

        monkeypatch.setattr(regeneration.visual_engine, "generate_scene_visual", generate)
        monkeypatch.setattr(regeneration.render_engine, "render_scene_clip", render_clip)
        monkeypatch.setattr(regeneration.render_engine, "concat_scene_clips", concat)
        monkeypatch.setattr(regeneration.render_engine, "probe_dimensions", probe)
        monkeypatch.setattr(regeneration.editing, "apply_edit", apply_edit)
        return self


# --- can this be done at all --------------------------------------------


def test_a_project_whose_working_files_were_swept_says_so(tmp_path, monkeypatch):
    """Every video rendered before this feature existed is in this state,
    and so is every video older than the retention window. The answer has
    to be an explanation, not a 500."""
    project = _project()
    monkeypatch.setattr(regeneration, "project_dir", lambda _id: tmp_path / "gone")

    ok, reason = regeneration.availability(project)

    assert ok is False
    assert "cleaned up" in reason


def test_a_half_swept_project_is_refused(finished, monkeypatch):
    """One clip short is not most of the way there — concat needs all of
    them, and a missing one would silently shorten the video."""
    project, paths = finished
    (paths / "output" / "clip_01.mp4").unlink()

    ok, _ = regeneration.availability(project)

    assert ok is False


def test_an_upload_has_no_scenes_to_redraw(finished):
    project, _ = finished
    project.source_path = "/somewhere/original.mp4"

    ok, reason = regeneration.availability(project)

    assert ok is False
    assert "Uploaded" in reason


def test_a_finished_generated_project_is_regenerable(finished):
    project, _ = finished

    assert regeneration.availability(project) == (True, None)


# --- the prompt ----------------------------------------------------------


def test_a_pasted_prompt_is_flattened_and_capped():
    cleaned = regeneration.sanitise_prompt("  a woman\n\nin a\tcafé  " + "x" * 900)

    assert "\n" not in cleaned and "\t" not in cleaned
    assert len(cleaned) <= 400


def test_an_empty_prompt_is_refused():
    with pytest.raises(NotRegenerable):
        regeneration.sanitise_prompt("   \n  ")


# --- doing it ------------------------------------------------------------


async def test_only_the_named_scene_is_redrawn(finished, monkeypatch):
    project, paths = finished
    engines = _Engines().install(monkeypatch, paths)

    await regeneration.regenerate_scene(project, 1, get_settings(), revision=1)

    assert engines.generated == [(1, 1)]
    assert engines.encoded == [1]


async def test_the_other_scenes_clips_are_reused_in_order(finished, monkeypatch):
    """Scene 10 has to land after scene 9, not after scene 1 — the concat
    list is built from a directory glob."""
    project, paths = finished
    engines = _Engines().install(monkeypatch, paths)

    await regeneration.regenerate_scene(project, 1, get_settings(), revision=1)

    assert engines.concatenated == [["clip_00.mp4", "clip_01.mp4", "clip_02.mp4"]]


async def test_the_new_clip_replaces_the_old_one_on_disk(finished, monkeypatch):
    project, paths = finished
    _Engines().install(monkeypatch, paths)

    await regeneration.regenerate_scene(project, 1, get_settings(), revision=1)

    assert (paths / "output" / "clip_01.mp4").read_bytes() == b"new clip"
    assert (paths / "output" / "clip_00.mp4").read_bytes() == b"clip 0"
    assert (paths / "output" / "concatenated.mp4").read_bytes() == b"new concat"


async def test_the_revision_counts_up_and_drives_the_stock_variant(finished, monkeypatch):
    """A stock search is deterministic, so asking again with the same
    prompt returns the same clip. The variant is what makes the second
    re-roll worth its credit."""
    project, paths = finished
    engines = _Engines().install(monkeypatch, paths)

    await regeneration.regenerate_scene(project, 0, get_settings(), revision=1)
    await regeneration.regenerate_scene(project, 0, get_settings(), revision=2)

    assert engines.generated == [(0, 1), (0, 2)]
    assert project.script.scenes[0].visual.revision == 2


async def test_an_edited_prompt_is_stored_as_well_as_used(finished, monkeypatch):
    """The Breakdown tab shows the prompt, and it has to say what actually
    produced the picture on screen."""
    project, paths = finished
    _Engines().install(monkeypatch, paths)

    await regeneration.regenerate_scene(
        project, 2, get_settings(), revision=1, prompt="a single face, close up"
    )

    assert project.script.scenes[2].visual.prompt == "a single face, close up"


async def test_a_negative_prompt_can_be_set_and_cleared(finished, monkeypatch):
    """The main reason to touch it: a hand came out wrong, so put hands in
    the negative. Clearing falls back to the art style's own."""
    project, paths = finished
    _Engines().install(monkeypatch, paths)

    await regeneration.regenerate_scene(project, 0, get_settings(), revision=1, negative_prompt="hands, feet")
    assert project.script.scenes[0].visual.negative_prompt == "hands, feet"

    await regeneration.regenerate_scene(project, 0, get_settings(), revision=2, negative_prompt="")
    assert project.script.scenes[0].visual.negative_prompt is None


async def test_the_visuals_directory_does_not_survive(finished, monkeypatch):
    """It was 91% of what cleanup reclaims. A re-roll draws into it and
    must not leave it behind, on either path."""
    project, paths = finished
    _Engines().install(monkeypatch, paths)

    await regeneration.regenerate_scene(project, 0, get_settings(), revision=1)

    assert not (paths / "visuals").exists()


async def test_a_failed_generation_leaves_the_old_video_alone(finished, monkeypatch):
    """Nothing is swapped until the new clip exists, so a generator that
    dies leaves the customer with the video they already had."""
    project, paths = finished
    engines = _Engines().install(monkeypatch, paths)

    async def explode(*args, **kwargs):
        raise RuntimeError("replicate said no")

    monkeypatch.setattr(regeneration.visual_engine, "generate_scene_visual", explode)

    with pytest.raises(RuntimeError, match="replicate"):
        await regeneration.regenerate_scene(project, 1, get_settings(), revision=1)

    assert (paths / "output" / "clip_01.mp4").read_bytes() == b"clip 1"
    assert (paths / "output" / "concatenated.mp4").read_bytes() == b"old concat"
    assert not (paths / "visuals").exists()
    assert engines.concatenated == []


# --- the timeline --------------------------------------------------------


async def test_the_timeline_does_not_move(finished, monkeypatch):
    """The whole reason the duration is pinned rather than re-probed. Every
    caption in the project is timed against the concatenated video, so a
    scene that comes back a frame longer desynchronises everything after
    it."""
    project, paths = finished
    project.captions = CaptionTrack(
        words=[Word(text="a", start_ms=0, end_ms=100), Word(text="b", start_ms=5000, end_ms=5100)],
        style=SubtitleStyle(),
    )
    _Engines().install(monkeypatch, paths)
    before = [(w.start_ms, w.end_ms) for w in project.captions.words]

    await regeneration.regenerate_scene(project, 0, get_settings(), revision=1)

    assert [(w.start_ms, w.end_ms) for w in project.captions.words] == before


async def test_a_scene_that_does_come_back_longer_shifts_only_what_follows(
    finished, monkeypatch
):
    """Defence in depth. If the encoder ever disagrees about the length,
    the words inside the re-drawn scene keep their timing and everything
    after it moves by exactly the difference."""
    project, paths = finished
    project.captions = CaptionTrack(
        words=[
            Word(text="inside", start_ms=100, end_ms=200),      # scene 0
            Word(text="after", start_ms=4000, end_ms=4100),     # scene 1
        ],
        style=SubtitleStyle(),
    )
    _Engines(new_duration_ms=4050).install(monkeypatch, paths)

    await regeneration.regenerate_scene(project, 0, get_settings(), revision=1)

    assert [(w.start_ms, w.end_ms) for w in project.captions.words] == [
        (100, 200),
        (4050, 4150),
    ]


async def test_captions_the_user_edited_are_not_replaced_by_the_transcript(
    finished, monkeypatch
):
    """The highest-value test here.

    Once a project has been through /edit, `edit.captions` is the
    authority and holds text the user typed. Rebuilding the track from
    `absolute_words(scenes)` — the obvious implementation — produces
    perfectly correct timings and silently throws the corrections away.
    Every other test in this file passes against that version.
    """
    project, paths = finished
    project.edit = EditSpec(
        captions=CaptionTrack(
            words=[Word(text="CORRECTED", start_ms=0, end_ms=500)],
            style=SubtitleStyle(),
        )
    )
    _Engines().install(monkeypatch, paths)

    await regeneration.regenerate_scene(project, 0, get_settings(), revision=1)

    assert [w.text for w in project.edit.captions.words] == ["CORRECTED"]


# --- refusing to make a broken video ------------------------------------


async def test_a_project_rendered_at_another_size_is_refused(finished, monkeypatch):
    """concat -c copy does not validate its inputs. Given a clip of a
    different size it emits a file that plays and then decodes as garbage,
    so the only safe answer is to decline before drawing anything."""
    project, paths = finished
    engines = _Engines().install(monkeypatch, paths)

    async def probe_square(path, ffprobe_binary="ffprobe"):
        return (1080, 1080)

    monkeypatch.setattr(regeneration.render_engine, "probe_dimensions", probe_square)

    with pytest.raises(NotRegenerable, match="different size"):
        await regeneration.regenerate_scene(project, 0, get_settings(), revision=1)

    assert engines.generated == []


async def test_the_outro_card_is_not_generated(finished, monkeypatch):
    """It is drawn locally from the operator's own text, so re-rolling it
    would spend a credit to produce the identical card."""
    project, paths = finished
    project.script.scenes[2].is_outro = True
    _Engines().install(monkeypatch, paths)

    with pytest.raises(NotRegenerable, match="closing card"):
        await regeneration.regenerate_scene(project, 2, get_settings(), revision=1)


async def test_a_scene_index_past_the_end_is_refused(finished, monkeypatch):
    project, paths = finished
    _Engines().install(monkeypatch, paths)

    with pytest.raises(NotRegenerable, match="3 scenes"):
        await regeneration.regenerate_scene(project, 9, get_settings(), revision=1)
