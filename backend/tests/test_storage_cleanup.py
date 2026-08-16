"""Deleting a project deletes what it produced.

The row was the only thing pointing at a project's files. Removing it and
leaving them behind means tens of megabytes per project that nothing will
ever reference again — and a user who asked for their video to be gone
still has it sitting on the server.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.core import storage
from app.core.config import get_settings, project_dir
from app.core.storage import discard_project_files


@pytest.fixture
def project_with_files(tmp_path, monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "storage_root", tmp_path)
    project_id = "a-project"
    paths = project_dir(project_id)
    (paths / "output" / "final.mp4").write_bytes(b"x" * 2048)
    (paths / "audio" / "scene_00.wav").write_bytes(b"y" * 1024)
    (paths / "visuals" / "scene_00.png").write_bytes(b"z" * 512)
    return project_id, tmp_path / project_id


def test_every_generated_file_is_removed(project_with_files):
    project_id, root = project_with_files
    assert root.exists()

    freed = discard_project_files(project_id)

    assert not root.exists()
    assert freed == 2048 + 1024 + 512


def test_a_project_with_nothing_on_disk_is_not_an_error(tmp_path, monkeypatch):
    """A render that failed before writing anything still gets deleted, and
    that must not turn into a 500 for the user."""
    monkeypatch.setattr(get_settings(), "storage_root", tmp_path)
    assert discard_project_files("never-rendered") == 0


def test_other_projects_are_untouched(project_with_files, tmp_path):
    project_id, _ = project_with_files
    neighbour = project_dir("someone-elses-project")
    (neighbour / "output" / "final.mp4").write_bytes(b"keep me")

    discard_project_files(project_id)

    assert (neighbour / "output" / "final.mp4").read_bytes() == b"keep me"


# --------------------------------------------------------------------------
# Intermediates
#
# 81% of a real install's 8.4GB was scaffolding from renders that had
# already finished. What matters here is that the sweep takes the right
# things — deleting concatenated.mp4 would silently break editing, which
# nothing would notice until someone tried to fix a caption.
# --------------------------------------------------------------------------


def _finished_project(root: Path, project_id: str = "proj") -> Path:
    base = root / project_id
    for sub in ("visuals", "audio", "output", "source", "subtitles"):
        (base / sub).mkdir(parents=True)
    (base / "output" / "final.mp4").write_bytes(b"x" * 1000)
    (base / "output" / "poster.jpg").write_bytes(b"x" * 10)
    (base / "output" / "concatenated.mp4").write_bytes(b"x" * 500)
    (base / "output" / "clip_00.mp4").write_bytes(b"x" * 300)
    (base / "output" / "clip_01.mp4").write_bytes(b"x" * 300)
    (base / "output" / "concat_list.txt").write_text("file 'a'")
    (base / "visuals" / "scene_00_stock.mp4").write_bytes(b"x" * 4000)
    (base / "audio" / "scene_00.wav").write_bytes(b"x" * 200)
    (base / "source" / "source.mp4").write_bytes(b"x" * 100)
    (base / "subtitles" / "captions.ass").write_text("[Events]")
    return base


def test_the_working_files_are_removed(tmp_path, monkeypatch):
    """The default sweep takes the visuals and leaves what a re-roll needs.

    `visuals/` was 6.2GB of the 6.8GB measured on a real install, so this
    still reclaims the overwhelming majority of it — and the picture is
    already inside the scene clip anyway, which is why a re-roll draws a
    new one rather than reusing this.
    """
    base = _finished_project(tmp_path)
    monkeypatch.setattr(get_settings(), "storage_root", tmp_path)

    freed = storage.discard_intermediates("proj")

    assert not (base / "visuals").exists()
    assert not (base / "output" / "concat_list.txt").exists()
    assert freed == 4000 + len("file 'a'")


def test_a_re_rolls_inputs_survive_the_default_sweep(tmp_path, monkeypatch):
    """Without both of these a finished project can never have one of its
    scenes re-drawn: render_scene_clip refuses without the voiceover, and
    concat needs every other scene's clip."""
    base = _finished_project(tmp_path)
    monkeypatch.setattr(get_settings(), "storage_root", tmp_path)

    storage.discard_intermediates("proj")

    assert (base / "audio" / "scene_00.wav").is_file()
    assert (base / "output" / "clip_00.mp4").is_file()
    assert (base / "output" / "clip_01.mp4").is_file()


def test_the_expiring_sweep_takes_them(tmp_path, monkeypatch):
    """What prune_storage.py runs once the retention window closes."""
    base = _finished_project(tmp_path)
    monkeypatch.setattr(get_settings(), "storage_root", tmp_path)

    freed = storage.discard_intermediates("proj", keep_reassembly_inputs=False)

    assert not (base / "audio").exists()
    assert not (base / "output" / "clip_00.mp4").exists()
    assert freed == 4000 + 200 + 300 + 300 + len("file 'a'")


def test_both_sweeps_are_idempotent(tmp_path, monkeypatch):
    """The sweeper has no state of its own and may see the same project on
    consecutive runs."""
    base = _finished_project(tmp_path)
    monkeypatch.setattr(get_settings(), "storage_root", tmp_path)

    storage.discard_intermediates("proj")
    storage.discard_intermediates("proj")
    assert storage.discard_intermediates("proj") == 0

    storage.discard_intermediates("proj", keep_reassembly_inputs=False)
    assert storage.discard_intermediates("proj", keep_reassembly_inputs=False) == 0

    # And neither pass ever touches the product.
    assert (base / "output" / "final.mp4").is_file()
    assert (base / "output" / "concatenated.mp4").is_file()


def test_the_file_editing_re_burns_from_is_kept(tmp_path, monkeypatch):
    """concatenated.mp4 is the pre-subtitle cut every edit is drawn onto.
    Losing it turns "fix a caption" into "re-render the whole video", and
    nothing would notice until someone tried."""
    base = _finished_project(tmp_path)
    monkeypatch.setattr(get_settings(), "storage_root", tmp_path)

    storage.discard_intermediates("proj")

    assert (base / "output" / "concatenated.mp4").is_file()


def test_the_video_and_its_poster_are_kept(tmp_path, monkeypatch):
    base = _finished_project(tmp_path)
    monkeypatch.setattr(get_settings(), "storage_root", tmp_path)

    storage.discard_intermediates("proj")

    assert (base / "output" / "final.mp4").is_file()
    assert (base / "output" / "poster.jpg").is_file()


def test_an_uploads_original_is_kept(tmp_path, monkeypatch):
    """Same role as concatenated.mp4, for a project that was uploaded."""
    base = _finished_project(tmp_path)
    monkeypatch.setattr(get_settings(), "storage_root", tmp_path)

    storage.discard_intermediates("proj")

    assert (base / "source" / "source.mp4").is_file()


def test_an_unfinished_render_is_left_alone(tmp_path, monkeypatch):
    """Without a final.mp4 the render either failed or is still going, and
    its inputs are the only copy of the work so far."""
    base = _finished_project(tmp_path)
    (base / "output" / "final.mp4").unlink()
    monkeypatch.setattr(get_settings(), "storage_root", tmp_path)

    assert storage.discard_intermediates("proj") == 0
    assert (base / "visuals" / "scene_00_stock.mp4").is_file()


def test_running_it_twice_is_harmless(tmp_path, monkeypatch):
    _finished_project(tmp_path)
    monkeypatch.setattr(get_settings(), "storage_root", tmp_path)

    storage.discard_intermediates("proj")

    assert storage.discard_intermediates("proj") == 0


def test_a_missing_project_is_not_an_error(tmp_path, monkeypatch):
    monkeypatch.setattr(get_settings(), "storage_root", tmp_path)

    assert storage.discard_intermediates("never-existed") == 0
