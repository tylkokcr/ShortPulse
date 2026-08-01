from pathlib import Path

from app.engines.subtitle_engine import build_ass_subtitles
from app.schemas.project import Scene, SceneAudio, SceneVisual, SubtitleStyle, Word


def _scene(index: int, words: list[Word]) -> Scene:
    return Scene(
        index=index,
        duration_s=4,
        visual=SceneVisual(prompt="a placeholder prompt"),
        audio=SceneAudio(
            voiceover_line=" ".join(w.text for w in words),
            duration_ms=words[-1].end_ms if words else 4000,
            words=words,
        ),
    )


def test_build_ass_subtitles_writes_events(tmp_path: Path):
    words = [
        Word(text="this", start_ms=0, end_ms=200),
        Word(text="is", start_ms=200, end_ms=350),
        Word(text="a", start_ms=350, end_ms=420),
        Word(text="test", start_ms=420, end_ms=800),
    ]
    scene = _scene(0, words)
    output_path = tmp_path / "captions.ass"

    result = build_ass_subtitles([scene], SubtitleStyle(), output_path)

    assert result == output_path
    content = output_path.read_text(encoding="utf-8")
    assert "[Events]" in content
    assert content.count("Dialogue:") == len(words)
    assert "THIS" in content  # uppercase=True by default


def test_build_ass_subtitles_offsets_multi_scene_timestamps(tmp_path: Path):
    scene_0 = _scene(0, [Word(text="hello", start_ms=0, end_ms=500)])
    scene_1 = _scene(1, [Word(text="world", start_ms=0, end_ms=500)])
    output_path = tmp_path / "captions.ass"

    build_ass_subtitles([scene_0, scene_1], SubtitleStyle(), output_path)

    lines = output_path.read_text(encoding="utf-8").splitlines()
    dialogue_lines = [line for line in lines if line.startswith("Dialogue:")]
    assert len(dialogue_lines) == 2
    # Second scene's word should start at scene_0's duration_ms offset (500ms), not 0.
    assert dialogue_lines[1].split(",")[1] == "0:00:00.50"
