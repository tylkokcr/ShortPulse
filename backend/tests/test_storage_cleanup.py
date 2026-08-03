"""Deleting a project deletes what it produced.

The row was the only thing pointing at a project's files. Removing it and
leaving them behind means tens of megabytes per project that nothing will
ever reference again — and a user who asked for their video to be gone
still has it sitting on the server.
"""

from __future__ import annotations

import pytest

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
