"""The Ken Burns move drawn with OpenCV: same frames, output size, no edges."""

from __future__ import annotations

import pytest

cv2 = pytest.importorskip("cv2")
np = pytest.importorskip("numpy")

from app.engines.render_engine import RenderTarget, _ken_burns_frames  # noqa: E402


def test_frames_are_the_target_size_and_count_and_move(tmp_path):
    # A smooth gradient: how much it moves shows as how much pixels change.
    ys, xs = np.mgrid[0:900, 0:600]
    image = np.dstack([(ys / 900 * 255), (xs / 600 * 255), ((ys + xs) / 1500 * 255)]).astype(np.uint8)
    path = tmp_path / "still.png"
    cv2.imwrite(str(path), image)

    frames = list(_ken_burns_frames(path, RenderTarget(width=270, height=480, fps=30), 0, 24))
    assert len(frames) == 24
    assert all(f.shape == (480, 270, 3) for f in frames)
    # It zooms in: the first and last frames differ, neighbours barely do.
    whole = np.abs(frames[0].astype(int) - frames[-1].astype(int)).mean()
    step = np.abs(frames[10].astype(int) - frames[11].astype(int)).mean()
    assert whole > 2 and step < whole / 3


def test_an_unreadable_still_falls_back_to_zoompan(tmp_path):
    bad = tmp_path / "missing.png"
    assert _ken_burns_frames(bad, RenderTarget(width=270, height=480, fps=30), 0, 10) is None
