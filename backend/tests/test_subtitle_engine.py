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


def test_turkish_uppercase_keeps_the_dotted_i(tmp_path: Path):
    """`str.upper()` turns Turkish "i" into "I", which is a different
    letter there — the caption reads RITME instead of RİTME. Burned into
    the frame, so there is no fixing it after the render."""
    words = [
        Word(text="sözlerin", start_ms=0, end_ms=300),
        Word(text="ritme", start_ms=300, end_ms=600),
    ]
    output_path = tmp_path / "captions.ass"

    build_ass_subtitles([_scene(0, words)], SubtitleStyle(), output_path, language="tr")

    content = output_path.read_text(encoding="utf-8")
    assert "SÖZLERİN" in content
    assert "RİTME" in content
    assert "RITME" not in content


def test_dotless_i_still_uppercases_to_plain_i(tmp_path: Path):
    """The other half of the Turkish pair: "ı" must stay dotless as "I",
    which is what str.upper() already does — the fix must not break it."""
    words = [Word(text="ışık", start_ms=0, end_ms=300)]
    output_path = tmp_path / "captions.ass"

    build_ass_subtitles([_scene(0, words)], SubtitleStyle(), output_path, language="tr")

    assert "IŞIK" in output_path.read_text(encoding="utf-8")


def test_non_turkish_uppercase_is_unchanged(tmp_path: Path):
    """English is the default and must not acquire dotted capitals."""
    words = [Word(text="vivid", start_ms=0, end_ms=300)]
    output_path = tmp_path / "captions.ass"

    build_ass_subtitles([_scene(0, words)], SubtitleStyle(), output_path, language="en")

    content = output_path.read_text(encoding="utf-8")
    assert "VIVID" in content
    assert "İ" not in content


# --- boxed captions ------------------------------------------------------


def test_a_boxed_style_asks_libass_for_a_filled_box():
    """BorderStyle 3 fills OutlineColour behind the text instead of
    stroking the glyphs with it. One number, and the only look a single
    bundled font could not otherwise produce."""
    from app.engines.subtitle_engine import _header_for
    from app.schemas.project import SubtitleStyle

    header = _header_for(SubtitleStyle(box=True), (1080, 1920))
    style_line = next(l for l in header.splitlines() if l.startswith("Style:"))

    # Name,Fontname,Fontsize,Primary,Secondary,Outline,Back,Bold,Italic,
    # Underline,StrikeOut,ScaleX,ScaleY,Spacing,Angle,BorderStyle,...
    assert style_line.split(",")[15] == "3"


def test_an_ordinary_style_still_asks_for_an_outline():
    from app.engines.subtitle_engine import _header_for
    from app.schemas.project import SubtitleStyle

    header = _header_for(SubtitleStyle(), (1080, 1920))
    style_line = next(l for l in header.splitlines() if l.startswith("Style:"))

    assert style_line.split(",")[15] == "1"


def test_a_boxed_active_word_recolours_the_box_not_the_letters():
    """\\3c is the box under BorderStyle 3. Recolouring the text there
    would put the highlight against a filled background and lose it."""
    from app.engines.subtitle_engine import _render_line_text, SubtitleLine
    from app.schemas.project import SubtitleStyle, Word

    line = SubtitleLine(
        words=[Word(text="a", start_ms=0, end_ms=100), Word(text="b", start_ms=100, end_ms=200)],
        start_ms=0,
        end_ms=200,
    )
    style = SubtitleStyle(box=True, highlight_color="&H000045FF")

    text = _render_line_text(line, active_index=0, style=style, language="en")

    assert "\\3c&H000045FF" in text
    # No scale-up: it would make the active word's box taller than the
    # ones beside it and put a lump in the strip.
    assert "\\fscx" not in text


def test_an_outlined_active_word_still_grows_and_recolours_the_text():
    from app.engines.subtitle_engine import _render_line_text, SubtitleLine
    from app.schemas.project import SubtitleStyle, Word

    line = SubtitleLine(words=[Word(text="a", start_ms=0, end_ms=100)], start_ms=0, end_ms=100)
    text = _render_line_text(line, active_index=0, style=SubtitleStyle(), language="en")

    assert "\\fscx112" in text
    assert "\\3c" not in text


# --- fonts that can actually draw the language ---------------------------


def test_arabic_gets_a_font_that_has_arabic():
    """The bug this map was written for: Montserrat has no Arabic glyphs,
    libass does not say so, and every caption came out an empty box."""
    from app.engines.subtitle_engine import font_for

    assert font_for("Montserrat", "ar") == "Noto Sans Arabic"


def test_a_display_face_is_kept_where_it_covers_the_language():
    from app.engines.subtitle_engine import font_for

    assert font_for("Anton", "tr") == "Anton"


def test_a_display_face_is_swapped_out_where_it_does_not():
    """Latin-only by nature. The style is a preference; the alphabet is
    not, so the language wins."""
    from app.engines.subtitle_engine import font_for

    assert font_for("Anton", "ru") == "Montserrat"
    assert font_for("Anton", "ar") == "Noto Sans Arabic"


def test_permanent_marker_loses_turkish_specifically():
    """It has no ğ, ş or ı — measured from the file, not assumed."""
    from app.engines.subtitle_engine import font_for

    assert font_for("Permanent Marker", "tr") == "Montserrat"
    assert font_for("Permanent Marker", "en") == "Permanent Marker"


def test_every_font_named_in_the_coverage_map_actually_ships():
    """A preset naming a font that is not in the image renders in
    whatever libass finds instead, silently."""
    from fontTools.ttLib import TTFont

    from app.core.config import FONTS_DIR
    from app.engines.subtitle_engine import FONT_COVERAGE

    families = set()
    for path in FONTS_DIR.glob("*.ttf"):
        font = TTFont(path, fontNumber=0, lazy=True)
        families |= {str(r) for r in font["name"].names if r.nameID == 1}

    assert set(FONT_COVERAGE) <= families


def test_the_coverage_map_matches_what_the_files_contain():
    """Measured rather than declared: a font that loses a glyph in an
    upstream update should fail here, not in somebody's video."""
    from fontTools.ttLib import TTFont

    from app.core.config import FONTS_DIR
    from app.engines.subtitle_engine import FONT_COVERAGE

    probes = {
        "en": "Hello", "tr": "ğşıİ", "es": "ñáé", "fr": "àçê", "de": "äöüß",
        "pt": "ãõçá", "it": "àèìòù", "ru": "Привет", "ar": "مرحبا",
    }

    by_family = {}
    for path in FONTS_DIR.glob("*.ttf"):
        font = TTFont(path, fontNumber=0)
        codepoints = set()
        for table in font["cmap"].tables:
            codepoints |= set(table.cmap)
        for record in font["name"].names:
            if record.nameID == 1:
                by_family[str(record)] = codepoints

    for family, languages in FONT_COVERAGE.items():
        drawable = {
            lang for lang, sample in probes.items()
            if all(ord(ch) in by_family[family] for ch in sample)
        }
        assert drawable == set(languages), f"{family}: file says {sorted(drawable)}"
