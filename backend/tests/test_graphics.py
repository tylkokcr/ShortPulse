"""Info graphics: what the script asks for is what the caption file draws."""

from __future__ import annotations

from types import SimpleNamespace

from app.engines import graphics, subtitle_engine
from app.engines.script_engine import _counter, _scene_graphic
from app.schemas.project import (
    GraphicCounter,
    Scene,
    SceneAudio,
    SceneGraphic,
    SceneVisual,
    ScriptOutput,
    SubtitleStyle,
)


def _scene(i: int, graphic: SceneGraphic | None = None) -> Scene:
    return Scene(
        index=i,
        duration_s=3,
        visual=SceneVisual(prompt="p"),
        audio=SceneAudio(voiceover_line="l", duration_ms=3000),
        graphic=graphic,
    )


SCENES = [
    _scene(0),
    _scene(1, SceneGraphic(stamp="yok")),
    _scene(2, SceneGraphic(tally="Nintendo", icon="game")),
    _scene(3, SceneGraphic(tally="Sushi", icon="fish", stamp="bitti")),
    _scene(4),
]


def test_rows_stamps_and_the_counter_are_drawn_on_the_timeline():
    plan = graphics.Plan(
        counter=GraphicCounter(label="Japonya nüfusu", start=124_000_000, end=0),
        title="Japonya'sız dünya",
    )
    lines = graphics.events(SCENES, plan, "&H0000D7FF", "tr", "Montserrat")
    rows = [line for line in lines if "GfxList" in line and "\\move" in line]
    assert [("🎮" in r, "Nintendo" in r) for r in rows[:1]] == [(True, True)]
    assert "🐟" in rows[1] and "Sushi" in rows[1]
    # A row arrives with its scene: Nintendo is scene 2, which starts at 6s.
    assert rows[0].split(",")[1] == "0:00:06.08"
    stamps = [line for line in lines if "GfxStamp" in line]
    assert len(stamps) == 2 and "BİTTİ" in stamps[1]  # Turkish dotted capital
    counter = [line for line in lines if "GfxCounter" in line]
    assert "124.000.000" in counter[1] and counter[-1].rstrip().endswith("}0")
    assert "&H0000D7FF" in counter[-1]
    assert any("JAPONYA'SIZ DÜNYA" in line for line in lines)


def test_the_count_runs_when_the_map_goes_out_and_waits_for_a_card():
    from app.schemas.project import MapSpec

    scenes = [_scene(i) for i in range(4)]
    scenes[2].map = MapSpec(focus=["JPN"], action="vanish")
    plan = graphics.Plan(counter=GraphicCounter(label="Japonya nüfusu", start=124_000_000, end=0))

    def first_step(scenes):
        lines = [x for x in graphics.events(scenes, plan, "&H0000D7FF", "tr", "M") if "GfxCounter" in x]
        return lines[1].split(",")[2]  # when the starting number gives way

    # Scene 2 starts at 6s; the flicker begins half a second in.
    assert first_step(scenes) == "0:00:06.50"
    scenes[2].card = True
    assert first_step(scenes) == "0:00:08.30"


def test_the_styles_reach_the_caption_header(tmp_path):
    styles = graphics.styles("Montserrat", "&H0000D7FF")
    path = subtitle_engine.build_ass_from_words(
        [], SubtitleStyle(), tmp_path / "c.ass", extra_styles=styles, extra_events=["Dialogue: x"]
    )
    text = path.read_text()
    assert text.index("Style: GfxStamp") < text.index("[Events]")
    assert text.rstrip().endswith("Dialogue: x")


def test_only_what_if_draws_by_default_and_the_toggle_wins():
    script = ScriptOutput(topic="t", hook="h", scenes=SCENES, total_duration_s=15)
    what_if = SimpleNamespace(info_graphics=None, script_format="what_if")
    free = SimpleNamespace(info_graphics=None, script_format="free")
    off = SimpleNamespace(info_graphics=False, script_format="what_if")
    on = SimpleNamespace(info_graphics=True, script_format="free")
    assert graphics.plan_from(what_if, script) is not None
    assert graphics.plan_from(free, script) is None
    assert graphics.plan_from(off, script) is None
    assert graphics.plan_from(on, script) is not None
    bare = ScriptOutput(topic="t", hook="h", scenes=[_scene(0)], total_duration_s=3)
    assert graphics.plan_from(what_if, bare) is None


def test_the_models_fields_are_cleaned_before_they_are_drawn():
    g = _scene_graphic({"tally": "  The   Witcher ", "icon": "Game", "stamp": ""})
    assert g is not None and g.tally == "The Witcher" and g.icon == "game" and g.stamp is None
    assert _scene_graphic({"tally": "x", "icon": "dragon"}).icon is None  # not in ICONS
    assert _scene_graphic({"icon": "game"}) is None
    assert _counter({"label": "Population", "start": "38000000"}).start == 38_000_000
    assert _counter({"label": "Population", "start": 5, "end": 9}) is None
    assert _counter({"label": "Türkiye", "start": 1, "end": 0}) is None  # one country, not people
    assert _counter("38 million") is None


def test_braces_from_the_model_cannot_open_an_override_block():
    scenes = [_scene(0), _scene(1, SceneGraphic(tally="{\\\\fs400}huge", icon="game"))]
    line = next(x for x in graphics.events(scenes, graphics.Plan(), "&H0000D7FF", "en", "M") if "huge" in x)
    assert "\\fs400" not in line


def test_a_series_says_which_episode_it_is_and_counts_up():
    from app.schemas.project import MapSpec

    scenes = [_scene(i, SceneGraphic(tally="Radyo", icon="radio") if i == 2 else None) for i in range(4)]
    scenes[1].map = MapSpec(focus=["TUR"], action="spread")
    script = ScriptOutput(
        topic="x", hook="h", scenes=scenes, total_duration_s=12, episode=3,
        counter=GraphicCounter(label="Enfekte", start=12, end=240_000),
    )
    config = SimpleNamespace(info_graphics=None, script_format="outbreak", language="tr")
    plan = graphics.plan_from(config, script)
    assert plan is not None and plan.tag == "KURGU · BÖLÜM 3"
    lines = [x for x in graphics.events(scenes, plan, "&H0000D7FF", "tr", "M") if "GfxCounter" in x]
    assert lines[1].split(",")[2] == "0:00:03.30"  # with the first spread, not before
    assert lines[-1].rstrip().endswith("240.000")


def test_an_outbreak_count_climbs_through_every_map_of_it():
    from app.schemas.project import MapSpec

    scenes = [_scene(i) for i in range(6)]
    scenes[1].map = MapSpec(focus=["TUR"], action="spread")
    scenes[4].map = MapSpec(focus=["TUR"], action="spread")
    plan = graphics.Plan(counter=GraphicCounter(label="Enfekte", start=1, end=1840))
    lines = [x for x in graphics.events(scenes, plan, "&H0000D7FF", "tr", "M") if "GfxCounter" in x]
    # The last step lands at the end of the last map scene (15s), not 1.5s in.
    assert lines[-1].split(",")[1] >= "0:00:14.00"
